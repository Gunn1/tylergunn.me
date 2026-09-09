---
title: Threat modelling a homelab like it's production
slug: hardening-homelab
date: 2026-02-19
description: What actually moved the needle when I stopped treating my home network as a toy.
tags: blue team, homelab, netsec
---

For years my homelab security was a firewall rule and optimism. Then I actually wrote down what I was defending against, and most of what I had been doing turned out to be irrelevant.

## Write the model down first

The exercise that changed things was boring: a table of what I have, who might want it, and what they would have to do.

| Asset | Adversary | Realistic path in |
| --- | --- | --- |
| Backups, documents | Opportunistic scanner | Exposed service with a known CVE |
| Home automation | Same | Default credentials on an IoT device |
| Source code, keys | Targeted | Phished credential, then lateral movement |
| Bandwidth | Botnet | Anything with a shell and a public port |

Two things fell out of this immediately. Almost every realistic path started with **something I had exposed on purpose and then forgotten about**, and the IoT devices were the weakest link by a wide margin while holding nothing I cared about.

## What actually helped

### Stop exposing things

I had eleven ports forwarded. I could justify three. The rest were experiments from years earlier that I had never turned off, including a Jellyfin instance two major versions behind.

Everything that did not need to be public went behind Wireguard. This single change removed more attack surface than everything else combined, and it cost me nothing in convenience once the phone had a persistent tunnel.

> If you can only do one thing: enumerate what you have exposed, from the outside, and turn off everything you cannot justify out loud.

### Segment the untrusted devices

The IoT VLAN was the second-biggest win. Smart plugs, TVs and cameras go on a network that can reach the internet and nothing else. No amount of vendor firmware negligence turns into a foothold on the network holding my backups.

The rule that matters is the one denying inter-VLAN traffic by default. It is easy to create the VLAN, feel productive, and never actually write the deny rule.

### Watch for changes, not for attacks

I do not have the time or the volume to run a real detection stack, and pretending otherwise produces alerts nobody reads. What I run instead is a nightly diff:

```python
def diff_scan(previous: dict, current: dict) -> list[str]:
    """Report services that appeared, vanished, or changed banner."""
    changes = []
    for key in previous.keys() | current.keys():
        before, after = previous.get(key), current.get(key)
        if before == after:
            continue
        if before is None:
            changes.append(f"NEW      {key}: {after}")
        elif after is None:
            changes.append(f"GONE     {key}: {before}")
        else:
            changes.append(f"CHANGED  {key}: {before} -> {after}")
    return changes
```

Scan the perimeter, compare to yesterday, mail me only if something moved. Most days it sends nothing. When it does send something, it is always worth reading — which is the property that makes people actually read it.

### Patch the things that face outward

Unattended upgrades on everything public. For containers, a weekly pull and restart. This is unglamorous and it addresses the single most common path in the table above.

## What did not help

- **Fail2ban on SSH.** Once SSH was key-only and behind the tunnel, the log noise it was suppressing did not matter.
- **An IDS on the home network.** I ran Suricata for two months. It produced thousands of alerts about my own devices and I found nothing. The signal-to-noise ratio at this scale does not justify it.
- **Rotating passwords on a schedule.** A password manager with unique credentials everywhere made this pointless.
- **Obsessing over the router firmware.** Real, but far less likely than the forgotten Jellyfin port.

## The pattern

Every improvement that mattered was about **reducing what exists**, not adding a defensive layer. Fewer exposed ports, fewer devices that can talk to each other, fewer services running that nobody uses.

The stuff that did not help was almost all additive — another tool, another log source, another dashboard. It felt productive and it defended against nothing that was going to happen to me.

Write the table. It takes an hour and it tells you which half of your effort is wasted.
