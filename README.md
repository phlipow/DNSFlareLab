# DNSFlare Lab (Personal PoC)

This repository contains my personal DNSFlare lab, built to reproduce and study DNS timing side-channel behavior in a controlled environment.

Reference paper:
https://www.usenix.org/system/files/usenixsecurity25-moav.pdf

## Introduction:

DNS FLaRE is a DNS cache timing side-channel that targets the DNS forwarder cache. The attacker doesn't need direct network position or malware, the only requirement is that the any device connected to the network opens an attacker-controlled webpage and keeps it active in the background.

While multiple caches operate near the client (browser cache, OS-level cache, forwarder cache), the forwarder cache has some properties that can be exploited by an attacker:
- it is shared by multiple devices/users in the same network
- it is relatively small compared to browser/OS caches
- it can be flushed more easily than larger caches

This creates a measurable HIT/MISS timings:
- **cache HIT:** target DNS data is already in forwarder cache, so query path is short
- **cache MISS:** query must be resolved upstream, so path is longer

The attack adapts the classic flush-reload side-channel pattern to DNS, in repeated cycles:
1. **Flush:** The attacker fills the forwarder with attacker-controlled dummy DNS records to evict prior entries
2. **Sample interval:** A waiting window where victim activity may reinsert targeted domains in the shared forwarder cache
3. **Reload and timing:** The attacker triggers DNS-dependent browser requests for target domains and measures timing to infer cache state
4. **Classification:** Timings are compared against a calibrated model to classify HIT or MISS for each domain

Due to a browser property involving non-standard HTTPS ports—where queries are made for prefixed names like `_0._https.example.` com, this record is prefetched first to prevent noise and stabilize the timing.

To avoid reusing browser DNS cache, we can use browser cache partitioning that was intended to reduce cross-site leaks. By rotating attacker origins, we prevent browser cache from serving results, ensuring that each timing measurement reflects forwarder cache state rather than browser cache hits.

Security and Privacy Implications:
- An attacker can infer if specific domains were likely accessed in a recent time window.
- Because forwarder cache is shared across multiple devices, one victim session can leak activity patterns of other household members.
- This can extend to IoT operation profiling (activity inference from device-specific DNS patterns).

The paper notes that DNSSEC and DoH do not inherently remove this side-channel if the destination resolver/forwarder still exposes vulnerable shared-cache behavior.

This repository is an educational lab implementation of these ideas, intended for controlled security research and reproducibility.

## Lab Structure

This lab has five main files that work together:
- [Server.py](Server.py): Flask server and decision logic
- [static/stager.js](static/stager.js): browser-side orchestrator and timing collector
- [DNSFowarder.py](DNSFowarder.py): intentionally vulnerable DNS cache forwarder
- [setup.sh](setup.sh): environment setup and teardown automation
- [victim.sh](victim.sh): victim-like DNS activity simulator

These components interact to simulate and measure the timing attack through the following sequence:
1. The browser loads the Flask page from [Server.py](Server.py)
2. The page injects runtime config and executes [static/stager.js](static/stager.js)
3. The stager cycles through calibration and attack modes, measures timings, and posts results to the Flask endpoints
4. DNS queries are routed through [DNSFowarder.py](DNSFowarder.py), which exposes observable HIT/MISS latency differences
5. [victim.sh](victim.sh) keeps querying chosen domains, creating realistic cache repopulation behavior

### Setting up the Environment

[setup.sh](setup.sh) automates the configuration, initialization, and teardown of the lab environment. It must be executed with root privileges (`sudo`).

**1. Initial Setup (`--install`)**
Used for the first execution. It installs dependencies and configures the system constraints:
- Downloads and extracts the vulnerable Chromium v133 snapshot to `./chrome_v133`
- Creates a Python virtual environment (`.venv`) and installs `dnslib` and `flask`
- Configures an `iptables` rule to reject outbound TCP connections to port 0
- Overrides `/etc/resolv.conf` to force local DNS resolution (`nameserver 127.0.0.1`)
- Gives execution permissions to [victim.sh](victim.sh)
- Activates the virtual environment

**2. Routine Execution (No flag)**
Used when the lab is already installed but system settings need to be reapplied (e.g., after a reboot or network reset):
- Skips the Chromium download and Python dependency installation
- Reapplies the `iptables` rule blocking port 0
- Reapplies the `/etc/resolv.conf` local resolver override
- Activates the virtual environment

**3. Teardown (`--cleanup`)**
Used to restore the system to its original state after testing:
- Deactivates the virtual environment
- Removes the `iptables` rule for port 0
- Restores standard DNS resolution by clearing `/etc/resolv.conf` and restarting `NetworkManager`
- Deletes the temporary Chromium profile directory (`/tmp/chromium-DNSFlare`)

### Proof of Concept:

#### Server Side [Server.py](Server.py):

The server's primary role is hosting the web interface and processing incoming calibration and attack measurements. It utilizes these metrics to compute and store per-target thresholds, concluding its execution loop by logging the final HIT or MISS predictions.

Functions:
1. `index()`
- Serves HTML + bootstraps `window.DNSFlareConfig`
- Links server-side config into client-side script
- Loads the [stager.js](static/stager.js) script that runs the attack logic in the browser

2. `calibrate()`
- Receives `{target, hit, miss, iteration}` and appends values into `CALIBRATION[target]['hits']` and `CALIBRATION[target]['misses']`
- On final iteration, computes: $threshold = (median(HITs) + median(MISSes)) / 2$

2. `attack()`
- Receives `{target, time}` and compares `time` against `CALIBRATION[target]['threshold']`
- Predicts HIT when `time <= threshold`, else MISS
- Logs each prediction, does not retrain threshold during attack phase

#### Client Side [stager.js](static/stager.js):

The client-side script, executing the attack-state machine. It is responsible for generating cache pressure, measuring timing differences, and transmitting information to the server.

Functions:
1. `flush()`
- Generates fetches to `f0..f19.s2.mov.lat`
- This creates malicious dummy DNS entries (100 per fetch) that fill the forwarder cache and evict prior entries, including the target domains

2. `measureTime(domain)`
- Performs preparatory probe, then measures elapsed time around `fetch('http://' + domain + ':0/')`
- Measures and returns the timing, COMPLETE the side-channel

3. `main()`
- Executes the flow:
  - `start`
  - `calibrate_miss`
  - `calibrate_hit`
  - `attack` (loop)
- Saves states via url query parameters
- Posts calibration payloads to `/calibrate`
- Posts attack payloads to `/attack`
- Rotates origins and repeats indefinitely

### Vulnerable DNS Forwarder:

[DNSFowarder.py](DNSFowarder.py) is intentionally built as a vulnerable DNS cache component for testing purposes.

Our DNS forwarder is binded to 127.0.0.1:53 for intercepting DNS requests. It directly returns 127.0.0.1 for .localhost. A queries, while for all other domains, it first checks its internal queue cache. On a cache MISS, it forwards the request to an upstream resolver (8.8.8.8), zeroes out the TTL in the response objects, and inserts the resulting A records into its local queue.

This component is vulnerable because, unlike modern forwarders that allocate one cache slot per domain, this implementation utilizes an IP-bound First-In-First-Out architecture where each returned IP address consumes a separate slot. This fragile queue management is explicitly exploited using a Proof-of-Concept adaptation that forces TCP connections for queries to the dummy domain s2.mov.lat. Because this domain returns 100 IP addresses—exceeding the standard 512-byte DNS UDP limit—the forced TCP ensures the massive payload is fully retrieved without truncation. Consequently, querying this single domain instantly floods and flushes the entire cache, allowing an attacker to effortlessly manipulate the cache state and infer domain membership through simple response-time observations.

### Victim Simulator Behavior: victim.sh

[victim.sh](victim.sh) simulates benign user behavior that periodically resolves target domains.


This script accepts one or more domains as arguments, executing `dig @127.0.0.1 <domain>` in an infinite loop every few seconds to periodically repopulate the cache. Since the attacker script cannot force victim accesses directly, this component is crucial for generating external cache activity. By simulating this realistic background user behavior, it enables the attacker-side classifier to continuously observe and measure the target domains' transitions from MISS to HIT over time.

## Differences From Original Artifact PoC

The implementation of this lab relies on choices prioritizing demonstration and validation purposes. Below is an overview of the primary design decisions adopted in this model and the technical trade-offs involved:

1. **Simpler classification model:** This lab uses per-target median midpoint thresholding to ensure higher interpretability, fewer dependencies, and easier debugging. However, this approach is less expressive than richer statistical or machine learning models in noisy environments.

2. **Explicit client-side state machine:** State control is centralized in static/stager.js by url query parameters to provide clearer observability and easier iteration. The trade-off is that the constant URL updates and prominent browser orchestration make the execution noisy and highly detectable.

3. **Config-driven experimentation:** Targets and timing behavior are configured as runtime parameters to make repeated experiments easier without requiring code edits.

4. **Operational observability:** The system logs explicitly separate the calibration and attack phases using timestamped lines to facilitate easier interpretation and reproducibility.

## Results
By analyzing the synchronized logs across the Attacker (Terminal 1), DNS Forwarder (Terminal 2), and Victim (Terminal 4), we can clearly observe the successful exploitation of the DNS cache side-channel. The attack correctly infers user activity purely through timing variations.

### 1. Calibration Phase (19:31:37 - 19:32:13)
The attacker script first profiles the environment to establish reliable timing thresholds
- **Terminal 1** records timing variations between simulated cache hits and misses for the target domains
- **Terminal 2** confirms the mechanics, showing alternating `[MISS]` (fetching from `8.8.8.8`) and `[HIT]` resolutions, interspersed with massive cache cycling using the `s2.mov.lat` domains to forcefully flush the queue
- **Calculated Thresholds:** The script establishes the boundary at `14.15ms` for `vimeo.com` and `17.75ms` for `instagram.com`

### 2. Idle Attack Phase (19:32:22 - 19:32:56)
The attacker transitions into the active monitoring loop.
- **Terminal 4:** The victim is currently inactive
- **Terminal 1:** The script correctly predicts `MISS` for both `vimeo.com` and `instagram.com`, response times remain above the thresholds, frequently hitting the 80-120ms range due to upstream queries

### 3. Victim Accesses Target 1: vimeo.com (19:32:58 - 19:33:43)
- **Terminal 4:** At `19:32:58`, the victim script simulates a user actively browsing `vimeo.com`, periodically querying the domain
- **Terminal 2:** The forwarder logs show `vimeo.com` continually being loaded into the cache due to the victim's background activity, naturally fighting back against the attacker's cache evictions
- **Terminal 1:** At `19:33:04`, the attacker's browser registers a steep drop in resolution time for `vimeo.com` (3.10ms), correctly prediction `HIT`. It consistently tracks this state, while `instagram.com` correctly remains a `MISS`

### 4. Victim Switches to Target 2: instagram.com (19:34:16 - 19:34:55)
- **Terminal 4:** The victim terminates the `vimeo.com` session and begins accessing `instagram.com` at `19:34:16`
- **Terminal 1:** By `19:34:21`, the attacker's timing measurements accurately reflect this behavioral shift. The `instagram.com` resolution drops to 3.10ms (`HIT`), while `vimeo.com` starves and spikes back up to 104.50ms (`MISS`)
- **Terminal 2:** Forwarder logs confirm `instagram.com` is now natively surviving in the cache, whereas `vimeo.com` requests are once again resulting in `MISS`es routed to `8.8.8.8`


## Usage Workflow

This is the recommended safe flow to reproduce the PoC.

### 1. Prepare Isolated Environment

- Prefer VM/sandbox
- Ensure you have `sudo` privileges
- Ensure no production-critical services depend on local DNS while testing

### 2. Clone and Install Lab

```bash
git clone https://github.com/phlipow/DNSFlareLab.git DNSFlareLab
cd DNSFlareLab
sudo ./setup.sh --install
```

### 3. Start Components

Terminal 1:

```bash
sudo ./.venv/bin/python Server.py --targets <domain1>[,<domain2>,...]
```

Terminal 2:

```bash
sudo ./.venv/bin/python DNSFowarder.py
```

Terminal 3:

```bash
./chrome_v133/chrome-linux/chrome \
  --user-data-dir=/tmp/chromium-DNSFlare \
  --test-type \
  --disable-background-timer-throttling \
  --ignore-certificate-errors \
  --no-sandbox \
  --disable-gpu \
  --explicitly-allowed-ports=0 \
  --disable-features=dns-over-https \
  --disable-host-cache
```

In Chromium, browse to: [http://127.0.0.1](http://127.0.0.1)

Terminal 4:

```bash
./victim.sh <domain1> <domain2>
```

### 4. Cleanup Immediately After Testing

```bash
sudo ./setup.sh --cleanup
```

### 6. Safety Notes

- This lab changes system resolver behavior and firewall rules
- Do not use this browser profile for normal browsing
- If cleanup fails, manually restore resolver/network and remove the iptables rule before leaving the lab environment
