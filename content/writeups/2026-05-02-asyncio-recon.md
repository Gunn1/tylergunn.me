---
title: Scanning 65k ports without melting your NIC
slug: asyncio-recon
date: 2026-05-02
description: Semaphores, backpressure, and why a naïve task-per-target asyncio scanner gets you rate-limited into oblivion.
tags: python, asyncio, networking
---

The first version of my scanner was four lines and completely useless:

```python
async def scan(targets):
    return await asyncio.gather(*(probe(t) for t in targets))
```

For sixty-five thousand ports this creates sixty-five thousand coroutines, every one of which immediately tries to open a socket. What happens next depends on which limit you hit first.

## The three walls you hit

**File descriptors.** The default soft limit is often 1024. You will see `OSError: [Errno 24] Too many open files` long before the scan finishes, and `asyncio.gather` will have already scheduled everything, so the failures cascade.

**Connection tracking.** If anything between you and the target keeps state — a home router, a firewall, a NAT — the table fills and it starts dropping *new* flows silently. Your scan reports closed ports that are open. This is the failure mode that matters, because it is wrong rather than merely broken.

**The remote end.** Anything doing rate limiting will tarpit or blackhole you, and your results become a measurement of the defender's policy rather than the target's ports.

> The naïve version is not slow. It is fast and wrong, which is worse.

## Bounding the work

The fix is a semaphore, and the important detail is *where* you acquire it:

```python
async def scan(targets: Iterable[Target], workers: int = 500) -> list[Result]:
    sem = asyncio.Semaphore(workers)

    async def bounded(t: Target) -> Result | None:
        async with sem:
            try:
                return await probe(t)
            except (OSError, asyncio.TimeoutError):
                return None

    results = await asyncio.gather(*map(bounded, targets))
    return [r for r in results if r is not None]
```

This still creates 65k coroutine objects, but only `workers` of them hold a socket at a time. A bare coroutine is roughly a few hundred bytes; a socket is a file descriptor and a kernel buffer. Bounding the expensive resource is what matters.

## When the target list does not fit in memory

`asyncio.gather` materialises every task up front. For a `/8` that is not acceptable. Use a queue and a fixed pool of workers instead:

```python
async def scan_streaming(targets, workers: int = 500):
    queue: asyncio.Queue[Target] = asyncio.Queue(maxsize=workers * 2)

    async def worker():
        while True:
            t = await queue.get()
            try:
                if (r := await probe(t)) is not None:
                    yield_result(r)
            finally:
                queue.task_done()

    pool = [asyncio.create_task(worker()) for _ in range(workers)]
    for t in targets:              # a generator, not a list
        await queue.put(t)         # blocks once the queue is full
    await queue.join()
    for w in pool:
        w.cancel()
```

The `maxsize` on the queue is the backpressure. Without it, the producer loop runs ahead and you are back to holding the whole target list in memory.

## Picking the number

There is no correct value for `workers`, but there is a correct way to find it. Ramp until the *error rate* rises, not until throughput stops improving — throughput keeps climbing for a while after you have started losing packets.

| Workers | Ports/sec | Timeouts | Verdict |
| --- | --- | --- | --- |
| 100 | 480 | 0.1% | Leaving speed on the table |
| 500 | 2,300 | 0.3% | Good |
| 2,000 | 5,100 | 4.2% | Losing real results |
| 10,000 | 6,000 | 31% | Measuring your own router |

On my connection 500 was the sweet spot. On yours it will be different, which is the point — hardcoding a number someone else published is how you get quiet false negatives.

## Timeouts are part of correctness

A too-short timeout turns a slow-but-open port into a closed one:

```python
async def probe(t: Target, timeout: float = 2.0) -> Result | None:
    try:
        async with asyncio.timeout(timeout):
            reader, writer = await asyncio.open_connection(t.host, t.port)
    except (OSError, TimeoutError):
        return None
    ...
```

`asyncio.timeout` is 3.11+ and much harder to misuse than `wait_for`, mainly because it composes properly with `except*` and does not swallow cancellation from an outer scope.

## The summary

- Bound the sockets, not the coroutines.
- Put a `maxsize` on the queue or you have not actually added backpressure.
- Tune against error rate, not throughput.
- Retry once before believing a closed port.

The scanner is about 300 lines now. The four-line version was faster to write and gave answers I could not trust.
