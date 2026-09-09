---
title: Walking a heap overflow to RCE, slowly
slug: heap-overflow-ctf
date: 2026-07-14
description: A full writeup of a glibc tcache poisoning chain, including every dead end I hit before the exploit landed.
tags: pwn, glibc, ctf
---

Most exploit writeups present a clean path from crash to shell. This is not that. This is the actual sequence, dead ends included, because the dead ends are where I learned the useful things.

## The bug

The target parsed a length-prefixed record format. The length was read as a signed 32-bit integer, validated against a maximum, and then used to size a heap allocation:

```c
int32_t len = read_i32(fd);
if (len > MAX_RECORD) return -1;
char *buf = malloc(len);
read(fd, buf, len);
```

The validation checks the upper bound but never the lower one. A negative length sails past the `>` comparison, gets implicitly converted to `size_t` at the `malloc` call, and becomes enormous — so `malloc` fails and returns `NULL`. Not obviously useful.

But `read` takes the same value, and on this build the return of `malloc` was never checked.

> A `NULL` write is usually a crash, not a primitive. The interesting part was what happened with lengths near the signed boundary.

## First dead end: chasing the NULL deref

I spent an afternoon trying to map a page at address zero. On a modern kernel `vm.mmap_min_addr` is 65536 and you cannot lower it without privileges you would not have if you already had the flag. This was never going to work, and I should have checked the sysctl before writing any code.

## The actual primitive

Lengths between `0x7fffffff` and the maximum passed validation while still being small enough after truncation to produce a *successful* allocation of a modest size. The `read` then used the untruncated value.

That is a linear heap overflow with attacker-controlled length and contents — the most forgiving primitive in the category.

## Shaping the heap

The allocator was glibc 2.35, so tcache was in play. The plan:

1. Allocate a run of same-size chunks so they land in a predictable order.
2. Free two of them into the tcache bin.
3. Overflow from an adjacent chunk into the `next` pointer of the head entry.
4. Allocate twice — the second allocation lands wherever the poisoned pointer points.

Since glibc 2.32, tcache `next` pointers are mangled:

```python
def mangle(pos: int, ptr: int) -> int:
    """glibc PROTECT_PTR: ptr ^ (address_of_slot >> 12)"""
    return ptr ^ (pos >> 12)
```

So step 3 needs a heap address leak before it can work at all. That cost me another few hours, because I assumed I could brute-force the low bits. You cannot — the mangling covers the whole pointer.

## Getting the leak

The record parser echoed back a fixed-size field from the record body without clearing the buffer between requests. Sending a short record left the tail of the previous allocation in place, which leaked a heap pointer from a freed chunk's `next` field.

With that, `pos >> 12` was known and the mangling became arithmetic.

## Landing the write

I pointed the poisoned allocation at `__free_hook`, which was the obvious move and also the wrong one — this build had `__free_hook` removed, as glibc did from 2.34 onward. Third dead end.

The version-appropriate target is the FILE vtable or, more simply here, a saved return address on a thread stack. I went with a one-gadget via the exit handler table:

| Target | glibc 2.35 | Notes |
| --- | --- | --- |
| `__free_hook` | removed | Wasted two hours |
| `__malloc_hook` | removed | Same |
| `_IO_2_1_stdout_` vtable | viable | Needs a larger write |
| `initial` exit handlers | viable | Needs `PTR_MANGLE` key |

The exit handler path needs the pointer guard from TLS, which I did not have. The FILE vtable path only needed the libc base, which the same uninitialised-memory leak provided.

## What actually worked

Overwrite `_IO_2_1_stdout_`'s vtable pointer to point into a fake vtable in known-writable memory, with the `_IO_overflow` slot pointing at a one-gadget. The next `puts` call triggered it.

```
$ ./exploit.py --host target --port 1337
[*] leaking heap ...      0x55f3c2a1b2a0
[*] leaking libc ...      0x7f2b41e00000
[*] poisoning tcache ...  ok
[*] triggering ...
[+] shell
$ id
uid=1000(ctf) gid=1000(ctf)
```

## Things worth keeping

- **Check the environment before writing the exploit.** The `mmap_min_addr` and the missing hooks were both one command away.
- **Version-match your technique.** Half of what is on the internet targets glibc 2.27 and silently does not apply.
- **An uninitialised-memory read is worth more than it looks.** One leak solved both the heap and libc problems.

The full exploit is about 120 lines of Python. The useful part was never the code.
