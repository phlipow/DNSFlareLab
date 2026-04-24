import socket
import threading
from dnslib import DNSRecord, QTYPE, RR, A, RCODE
from collections import deque
from datetime import datetime

LISTEN_IP = '127.0.0.1'
LISTEN_PORT = 53
UPSTREAM_DNS = '8.8.8.8'
UPSTREAM_PORT = 53
MAX_SLOTS = 500
TIMEOUT = 3.0

def timestamp():
    now = datetime.now()
    return f"{{{now.strftime('%H:%M:%S')}:{now.microsecond // 1000:03d}}} "

class DNSForwarder:
    def __init__(self):
        self.listen_ip = LISTEN_IP
        self.listen_port = LISTEN_PORT
        self.upstream_dns = UPSTREAM_DNS
        self.upstream_port = UPSTREAM_PORT
        self.max_slots = MAX_SLOTS
        self.timeout = TIMEOUT

        self.cache_queue = deque([{None: None} for _ in range(self.max_slots)], maxlen=self.max_slots)
        self.lock = threading.Lock()

    def get_from_queue(self, domain):
        with self.lock:
            ips = []
            for item in self.cache_queue:
                if domain in item:
                    ips.append(item[domain])
            return ips if ips else None

    def put_in_queue(self, domain, ips):
        with self.lock:
            count = 0
            for ip in ips:
                entry = {domain: ip}

                if entry not in self.cache_queue:
                    self.cache_queue.append(entry)
                    count += 1

            print(f"{timestamp()}[CACHED] Cache queue cycled with {count} new entries for {domain}.")

    def handle_query(self, data, addr, sock):
        try:
            request = DNSRecord.parse(data)
            qname = str(request.q.qname).lower()
            qtype = request.q.qtype
            qtype_name = QTYPE.get(qtype, str(qtype))
            reply = request.reply()

            if qname.endswith(".localhost.") and qtype == QTYPE.A:
                reply.add_answer(RR(qname, QTYPE.A, rdata=A("127.0.0.1"), ttl=0))
                sock.sendto(reply.pack(), addr)
                return

            else:

                cached_ips = self.get_from_queue(qname)
                if cached_ips and qtype == QTYPE.A:
                    print(f"{timestamp()}[HIT] {qname} ({qtype_name}) found on cache")
                    for ip in cached_ips:
                            reply.add_answer(RR(qname, QTYPE.A, rdata=A(ip), ttl=0))
                    sock.sendto(reply.pack(), addr)

                else:
                    print(f"{timestamp()}[MISS] {qname} ({qtype_name}) searching on {self.upstream_dns}...")
                    use_tcp = "s2.mov.lat" in qname
                    response_data = request.send(self.upstream_dns, self.upstream_port, tcp=use_tcp, timeout=self.timeout)
                    response_record = DNSRecord.parse(response_data)
                    ips_to_queue = []
                    for rr in response_record.rr:
                        rr.ttl = 0
                        if rr.rtype == QTYPE.A:
                            ips_to_queue.append(str(rr.rdata))

                    for auth in response_record.auth: auth.ttl = 0
                    for ar in response_record.ar: ar.ttl = 0

                    sock.sendto(response_record.pack(), addr)

                    if len(ips_to_queue) > 0: self.put_in_queue(qname, ips_to_queue)
                    else: print(f"{timestamp()}[ERROR] {qname} ({qtype_name}) received response without A records, not caching.")

        except Exception as e:
            print(f"{timestamp()}[ERROR] Failed to process query from {addr}: {e}")

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.listen_ip, self.listen_port))

        print(f"{timestamp()}DNSForwarder starting at {self.listen_ip}:{self.listen_port}")
        print(f"{timestamp()}Cache initialized with {self.max_slots} empty slots {{None: None}}")

        while True:
            data, addr = sock.recvfrom(4096)
            threading.Thread(target=self.handle_query, args=(data, addr, sock), daemon=True).start()

if __name__ == "__main__":
    DNSForwarder().start()