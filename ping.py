
"""
	A pure python ping implementation using raw sockets.

	Note that ICMP messages can only be send from processes running as root
	
"""


import os
import select
import signal
import struct
import sys
import time
import socket,sys
from impacket import ImpactPacket
from subprocess import check_output
# import ifaddr
from random import randint

HOST_COUNT = 4
HOME_RETURN_PAYLOAD_KEYWORD = "RET_HOME"
HOME_RETURN_REQUEST_TIMEOUT = 10

DATA_PAYLOAD_KEYWORD = "DATA"
PAYLOAD_DELIMITER = "|"

SEND_COMMAND_KEYWORD = "send"
GET_COMMAND_KEYWORD = "get"
QUIT_COMMAND_KEYWORD = "quit"

PAYLOAD_SIZE = 512
MAX_NUMBER_OF_CHUNKS_PER_FILE = 10



class Return_home_request:
	def __init__(self, src_ip, file_name):
		self.src_ip = src_ip
		self.file_name = file_name
		self.request_time = int(time.time())

	def is_expired(self):
		return int(time.time()) - self.request_time > HOME_RETURN_REQUEST_TIMEOUT

class Download_request:
	def __init__(self, file_name, ):
		self.number_of_caught_packets = 0
		self.file_name = file_name
		self.received_payloads = [''] * MAX_NUMBER_OF_CHUNKS_PER_FILE





if sys.platform.startswith("win32"):
	# On Windows, the best timer is time.clock()
	default_timer = time.clock
else:
	# On most other platforms the best timer is time.time()
	default_timer = time.time


# ICMP parameters
ICMP_ECHOREPLY = 0 # Echo reply (per RFC792)
ICMP_ECHO = 8 # Echo request (per RFC792)
ICMP_MAX_RECV = 2048 # Max size of incoming buffer

MAX_SLEEP = 1000


def get_my_ip():
	ips = check_output(['hostname', '--all-ip-addresses'])
	return ips.split(' ')[0]

def is_valid_ip4_address(addr):
	parts = addr.split(".")
	if not len(parts) == 4:
		return False
	for part in parts:
		try:
			number = int(part)
		except ValueError:
			return False
		if number > 255 or number < 0:
			return False
	return True

def to_ip(addr):
	if is_valid_ip4_address(addr):
		return addr
	return socket.gethostbyname(addr)


class Response(object):
	def __init__(self):
		self.max_rtt = None
		self.min_rtt = None
		self.avg_rtt = None
		self.packet_lost = None
		self.ret_code = None
		self.output = []

		self.packet_size = None
		self.timeout = None
		self.source = None
		self.destination = None
		self.destination_ip = None

class Ping(object):
	def __init__(self, source, destination, timeout=1000, packet_size=55, own_id=None, quiet_output=False, udp=False, bind=None):
		self.ip = get_my_ip()
		self.ret_home_requests = []
		self.downloading_files = []

		self.quiet_output = quiet_output
		if quiet_output:
			self.response = Response()
			self.response.destination = destination
			self.response.timeout = timeout
			self.response.packet_size = packet_size

		self.destination = destination
		self.source = source
		self.timeout = timeout
		self.packet_size = packet_size
		self.udp = udp
		self.bind = bind

		if own_id is None:
			self.own_id = os.getpid() & 0xFFFF
		else:
			self.own_id = own_id

		try:
			self.dest_ip = to_ip(self.destination)
			if quiet_output:
				self.response.destination_ip = self.dest_ip
		except socket.gaierror as e:
			self.print_unknown_host(e)
		else:
			self.print_start()

		self.seq_number = 0
		self.send_count = 0
		self.receive_count = 0
		self.min_time = 999999999
		self.max_time = 0.0
		self.total_time = 0.0

	#--------------------------------------------------------------------------

	def print_start(self):
		print("# Starting Network-Drive Node.")
		print("# Node ip: " + self.ip)

	def print_unknown_host(self, e):
		msg = "\nPYTHON-PING: Unknown host: %s (%s)\n" % (self.destination, e.args[1])
		if self.quiet_output:
			self.response.output.append(msg)
			self.response.ret_code = 1
		else:
			print(msg)

		raise Exception, "unknown_host"
		#sys.exit(-1)

	def print_exit(self):
		print("# Shutting down Network-Drive Node.")

	#--------------------------------------------------------------------------

	def signal_handler(self, signum, frame):
		"""
		Handle print_exit via signals
		"""
		self.print_exit()
		msg = "\n(Terminated with signal %d)\n" % (signum)

		if self.quiet_output:
			self.response.output.append(msg)
			self.response.ret_code = 0
		else:
			print(msg)

		sys.exit(0)

	def setup_signal_handler(self):
		signal.signal(signal.SIGINT, self.signal_handler)   # Handle Ctrl-C
		if hasattr(signal, "SIGBREAK"):
			# Handle Ctrl-Break e.g. under Windows 
			signal.signal(signal.SIGBREAK, self.signal_handler)

	#--------------------------------------------------------------------------

	def header2dict(self, names, struct_format, data):
		""" unpack the raw received IP and ICMP header informations to a dict """
		unpacked_data = struct.unpack(struct_format, data)
		return dict(zip(names, unpacked_data))

	#--------------------------------------------------------------------------

	def get_socket(self):
		try: 
			current_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
			current_socket.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

			# Bind the socket to a source address
			if self.bind:
				print('self.bind: ', self.bind)
				current_socket.bind((self.bind, 0)) # Port number is irrelevant for ICMP

		except socket.error, (errno, msg):
			if errno == 1:
				# Operation not permitted - Add more information to traceback
				#the code should run as administrator
				etype, evalue, etb = sys.exc_info()
				evalue = etype(
					"%s - Note that ICMP messages can only be sent from processes running as root." % evalue
				)
				raise etype, evalue, etb
			raise # raise the original error
		
		return current_socket

	#--------------------------------------------------------------------------

	def generate_return_home_payload(self, file_name):
		payload = PAYLOAD_DELIMITER.join([HOME_RETURN_PAYLOAD_KEYWORD, self.ip, file_name])
		return payload

	def generate_data_payload(self, file_name, data, total_chunks):
		payload = PAYLOAD_DELIMITER.join([DATA_PAYLOAD_KEYWORD, self.ip, file_name, str(total_chunks), data])
		return payload

	#--------------------------------------------------------------------------


	#--------------------------------------------------------------------------

	def download_file(self, file_name):
		self.downloading_files.append(Download_request(file_name))
		# TODO: add given file to waiting queue
		for i in range(1, HOST_COUNT + 1):
			dest_ip = "10.0.0." + str(i)
			if dest_ip == self.ip:
				continue

			current_socket = self.get_socket()
			payload = self.generate_return_home_payload(file_name)
			# print(payload)
			Ping.send_one_ping(current_socket, dest_ip, self.ip, 0, payload)
			print("# send retHome to " + dest_ip)
			current_socket.close()

	def upload_file(filename):
		pass
		# with open(filename, "r") as file:
		# 	payload = file.read(PAYLOAD_SIZE)

	#--------------------------------------------------------------------------

	def add_to_return_home_requests(self, src_ip, filename):
		req_obj = Return_home_request(src_ip=src_ip, file_name=filename)

		obj_added = False
		for i in range(0, len(self.ret_home_requests)):
			if self.ret_home_requests[i].is_expired():
				self.ret_home_requests[i] = req_obj
				obj_added = True
				break
		if not obj_added:
			self.ret_home_requests.append(req_obj)

	def check_if_data_requested(self, file_name):

		i = 0
		n = len(self.ret_home_requests)

		while (i < n):
			if self.ret_home_requests[i].is_expired():
				del ret_home_requests[i]
				n -= 1
			else :
				i += 1

		for req_obj in self.ret_home_requests:
			# if req_obj.src_ip == src_ip and req_obj.file_name == file_name:
			if req_obj.file_name == file_name:
				return req_obj
		return None

	def check_if_data_is_collected(self, file_name):
		for downloading_obj in self.downloading_files:
			if downloading_obj.file_name == file_name:
				return downloading_obj
		return None

	#--------------------------------------------------------------------------

	def run(self, count=None, deadline=None):
		"""
		send and receive pings in a loop. Stop if count or until deadline.
		"""
		if not self.quiet_output:
			self.setup_signal_handler()

		while True:
			if select.select([sys.stdin,],[],[],0.0)[0]:
				command = raw_input().split(' ')
				if command[0] == SEND_COMMAND_KEYWORD:
					pass
				elif command[0] == GET_COMMAND_KEYWORD:
					self.download_file(command[1])
				elif command[0] == QUIT_COMMAND_KEYWORD:
					break
				
			delay = self.do()

	def do(self):
		current_socket = self.get_socket()
		getPacket, icmp_header, payload = self.receive_one_ping(current_socket)
		if getPacket:
			parsed_payload = payload.split(PAYLOAD_DELIMITER)
			if parsed_payload[0] == HOME_RETURN_PAYLOAD_KEYWORD:
				self.add_to_return_home_requests(
					src_ip=parsed_payload[1],
					filename=parsed_payload[2]
				)
				print("recieved home return.")
			elif parsed_payload[0] == DATA_PAYLOAD_KEYWORD:
				downloading_obj = self.check_if_data_is_collected(parsed_payload[2])
				if downloading_obj:
						print("collecting packet.")
				else:
					req_obj = self.check_if_data_requested(parsed_payload[2])
					if req_obj:
						Ping.send_one_ping(current_socket, req_obj.src_ip, self.ip,
								icmp_header["packet_id"], payload)
						print("send packet to home.")
					
					else:
						self.resend_ICMP(current_socket, icmp_header, payload)
		current_socket.close()


	# send an ICMP ECHO_REQUEST packet
	@classmethod
	def send_one_ping(cls, current_socket, src, dst, icmp_packet_id, payload):
		
		#Create a new IP packet and set its source and destination IP addresses
		ip = ImpactPacket.IP()
		ip.set_ip_src(src)
		ip.set_ip_dst(dst)	

		#Create a new ICMP ECHO_REQUEST packet 
		icmp = ImpactPacket.ICMP()
		icmp.set_icmp_type(icmp.ICMP_ECHO)

		#inlude a small payload inside the ICMP packet
		#and have the ip packet contain the ICMP packet
		icmp.contains(ImpactPacket.Data(payload))
		ip.contains(icmp)


		#give the ICMP packet some ID
		icmp.set_icmp_id(icmp_packet_id)

		#set the ICMP packet checksum
		icmp.set_icmp_cksum(0)
		icmp.auto_checksum = 1

		send_time = default_timer()

		# send the provided ICMP packet over a 3rd socket
		try:
			current_socket.sendto(ip.get_packet(), (dst, 1)) # Port number is irrelevant for ICMP
		except socket.error as e:
			print("# socket creation failed.")
			current_socket.close()
			return

		return send_time


	def resend_ICMP(self, current_socket, icmp_header, payload):

		src = self.ip
		while (src == self.ip):
			src = "10.0.0." + str(randint(1, HOST_COUNT))
		
		dst = src
		while(dst == src):
			dst = "10.0.0." + str(randint(1, HOST_COUNT))
			
		# print "resending: " + src + "->" + dst
		send_time = Ping.send_one_ping(current_socket, src, dst, icmp_header["packet_id"], payload)
		return send_time
		
	# Receive the ping from the socket. 
	#timeout = in ms		

	def receive_one_ping(self, current_socket):
		
		timeout = self.timeout / 1000.0

		while True: # Loop while waiting for packet or timeout
			select_start = default_timer()
			inputready, outputready, exceptready = select.select([current_socket], [], [], timeout)
			
			select_duration = (default_timer() - select_start)
			if inputready == []: # timeout
				return False, None, None
			

			packet_data, address = current_socket.recvfrom(ICMP_MAX_RECV)

			icmp_header = self.header2dict(
				names=[
					"type", "code", "checksum",
					"packet_id", "seq_number"
				],
				struct_format="!BBHHH",
				data=packet_data[20:28]
			)

			receive_time = default_timer()

			# if icmp_header["packet_id"] == self.own_id: # Our packet!!!
			# it should not be our packet!!!Why?
			if True:
				ip_header = self.header2dict(
					names=[
						"version", "type", "length",
						"id", "flags", "ttl", "protocol",
						"checksum", "src_ip", "dest_ip"
					],
					struct_format="!BBHHHBBHII",
					data=packet_data[:20]
				)
				packet_size = len(packet_data) - 28
				ip = socket.inet_ntoa(struct.pack("!I", ip_header["src_ip"]))
				# XXX: Why not ip = address[0] ???
				# print "## Packet recevied."
				return True, icmp_header, packet_data[28:]

			timeout = timeout - select_duration
			if timeout <= 0:
				return False, None, None

def ping(source, hostname, timeout=1000, count=3, packet_size=55, *args, **kwargs):
	p = Ping(source, hostname, timeout, packet_size, *args, **kwargs)
	return p.run(count)

# ping("10.0.0.1", "10.0.0.2")

