---
title: Finding a critical attack chain in an ISP's monitoring platform
slug: isp-monitoring-disclosure
date: 2026-03-01
description: A regional ISP's LibreNMS portal was three years behind on patches. I replicated the stack in a lab, chained four bugs from customer account to root, and disclosed it. They rebuilt the whole server in a week.
tags: security research, disclosure, librenms, php
---

During routine use of a network monitoring portal provided by a regional ISP, I noticed the platform was advertising its own version numbers on the About page — and they were old. Three years old.

I built an isolated replica of their stack, validated a complete attack chain from a low-privilege customer account to full server compromise, and reported it. The ISP rebuilt their entire monitoring infrastructure within a week.

No testing of any kind was performed against the production system.

## Engagement summary

| Detail | Description |
| --- | --- |
| Target | LibreNMS network monitoring platform operated by a regional ISP |
| Scope | Application-layer vulnerabilities and attack chain validation |
| Approach | Source code review, isolated lab replication, exploit development |
| Access level | Low-privilege customer account (read-only, single port) |
| Environment | Isolated QEMU/KVM virtual machines; zero production testing |
| Outcome | Vendor rebuilt entire server stack within one week of disclosure |
| Severity | Critical |

## The target

The ISP issued customer accounts to their LibreNMS instance so we could monitor our own circuits. The About page disclosed detailed version information to any authenticated user, and the stack was significantly out of date:

| Component | Observed version | Status |
| --- | --- | --- |
| LibreNMS | 22.9.0 | 3+ years behind |
| PHP | 7.4.10 | EOL since Nov 2022 |
| Apache | 2.4.29 | 35+ missing security updates |
| Ubuntu | 18.04 LTS | EOL standard support May 2023 |
| MariaDB | 10.5.9 | Multiple updates pending |
| Laravel | 8.83.23 | End of life |
| Python | 3.6.9 | EOL since Dec 2021 |

The platform monitored 17 devices across the ISP's backbone — 1,175 ports, 350 sensors, 282 IPv4 addresses. A Weathermap plugin exposed the full backbone topology to every authenticated user, customer accounts included.

## Building the lab

Everything was validated in an isolated VM environment. Matching the production stack exactly mattered, because a bug that reproduces on PHP 8.3 tells you nothing about what is running on 7.4.10.

| VM | Role | Address | OS |
| --- | --- | --- | --- |
| LibreNMS server | Target replica | 192.168.100.10 | Ubuntu 18.04.6 LTS |
| VyOS router | Monitored device | 192.168.100.2 | VyOS Rolling |
| Kali Linux | Attack machine | 192.168.100.50 | Kali Linux |
| Host | Listener / C2 | 192.168.100.1 | Arch Linux |

### Compiling PHP 7.4.10 from source

Both the ondrej PPA and sury.org had dropped Bionic and PHP 7.4 support entirely, so there was no package to install. I pulled the exact 7.4.10 source tarball from php.net and compiled it with every extension LibreNMS needs — GD, MySQL, SNMP, LDAP, cURL — which surfaced the `--with-gd` to `--enable-gd` flag rename introduced in 7.4.

### Apache and Laravel

`mod_php` requires the prefork MPM, not the default event MPM. The symptom was an Apache error log line reading "Apache is running a threaded MPM" followed by a crash.

Composer also pulled updated Laravel packages that were incompatible with LibreNMS 22.9.0 — an `Exception` versus `Throwable` signature mismatch in the exception handler, patched in `Handler.php`.

### A real monitored device

The VyOS router provided realistic SNMP data: multiple interfaces, routing tables, and proper MIB responses, so LibreNMS discovered genuine ports with traffic statistics rather than empty stubs. The customer account was configured as Level 1 with visibility restricted to a single port, mirroring the ISP's access model.

## What the source review found

**Broken access control.** An AJAX endpoint accepted write operations from any authenticated user without checking whether that user had permission to modify the target resource. The source file contained no access control checks at all.

**Stored cross-site scripting.** Port description fields were rendered without `htmlspecialchars()` in the interface display template — while adjacent fields, like the event message, were properly escaped. A second vector existed in the eventlog type field via `formatType()`.

**SQL injection.** Two unsanitized concatenation points in the address search functionality: the IPv6 prefix and MAC address parameters used direct string interpolation rather than parameterized queries.

**Remote code execution.** The Blade template engine processed alert templates without sandboxing, so an `@php` directive in a template executed arbitrary system commands.

## The chain

Individually these are findings. Chained, they take a read-only customer account to root on a box holding credentials for the ISP's backbone.

1. **Authenticate** as a restricted customer — visibility limited to a single port.
2. **Broken access control** — write an XSS payload into *any* port's description via the unprotected AJAX endpoint.
3. **Stored XSS fires** when an admin views the device page and the unsanitized field renders.
4. **Session hijack** — the payload loads remote JavaScript from my server and uses the admin's session to create a malicious alert template.
5. **RCE** — the Blade template's `@php system()` directive executes as `www-data`, giving a reverse shell.
6. **Post-exploitation** — extract database credentials, application secrets, bcrypt password hashes, and plaintext SNMP community strings.

The pivot from step 2 is the interesting part. The account was scoped to one port, but the endpoint never checked that scope on write — so the restriction was purely a display-layer concern.

## Impact

| Data | Consequence |
| --- | --- |
| Database credentials | Full access to the application database |
| Application secret key | Decrypt any Laravel encrypted value |
| Password hashes | Bcrypt hashes extractable for offline cracking |
| SNMP community strings | Plaintext credentials for all 17 backbone devices |
| Network topology | Complete infrastructure map via SNMP enumeration |
| VAPID keys | Push notification signing keys |

Two local privilege escalation paths were also available: the alert processing script run by cron every minute was writable by the web server user through shared group membership, and the installed PolicyKit version was worth checking against CVE-2021-4034.

The SNMP community strings are the finding that matters most. With those, an attacker enumerates the ISP's entire network — routing tables, interface configurations, ARP tables, traffic statistics, optical signal levels on fiber links. The monitoring platform was a single point of compromise for the visibility layer of the whole backbone.

## Disclosure

The initial report was a high-level overview of the vulnerabilities and their impact, deliberately without exploit code or step-by-step reproduction. A detailed technical report with proof-of-concept material was written and held in reserve, to be shared only if their engineers asked for it.

The vendor acknowledged the same day — *"We'll be remediating in short order"* — and then did considerably more than patch:

| Component | Before | After |
| --- | --- | --- |
| LibreNMS | 22.9.0 | 26.4.1-dev |
| PHP | 7.4.10 (EOL) | 8.3.6 |
| Web server | Apache 2.4.29 | nginx 1.24.0 |
| MariaDB | 10.5.9 | 10.11.14 |
| Laravel | 8.83.23 | 12.48.1 |
| Python | 3.6.9 (EOL) | 3.12.3 |
| OS | Ubuntu 18.04 (EOL) | Ubuntu 24.04 LTS |

They rebuilt the server from scratch on a current OS with every component on a supported version. That is the right response and a rarer one than it should be.

## What I took from it

The vulnerabilities were not novel. Every one of them was a known class, in a known-outdated version, discoverable by reading the source. What made the assessment worth doing was the discipline around it: replicating the stack exactly rather than assuming, validating the full chain rather than reporting four separate findings, and testing nothing in production.

The version disclosure on the About page is what started all of it. A monitoring platform that tells every customer exactly how far behind it is has already given away the first step.
