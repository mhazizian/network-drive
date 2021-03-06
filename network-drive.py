import os
import select
import signal
import struct
import sys
import time
import socket,sys
from impacket import ImpactPacket
from subprocess import check_output
from random import randint
import threading

HOST_COUNT = 4
HOME_RETURN_PAYLOAD_KEYWORD = "RET_HOME"
HOME_RETURN_REQUEST_TIMEOUT = 10 #seconds

DATA_PAYLOAD_KEYWORD = "DATA"
PAYLOAD_DELIMITER = "|"
PAYLOAD_DATA_BEGIN = "@"
SEND_COMMAND_KEYWORD = "send"
GET_COMMAND_KEYWORD = "get"
QUIT_COMMAND_KEYWORD = "quit"

REPLY_TYPE = 0
REQUEST_TYPE = 8

PAYLOAD_SIZE = 1
MAX_NUMBER_OF_CHUNKS_PER_FILE = 100
SEND_DELAY_TIME = 0.05

if sys.platform.startswith("win32"):
	# On Windows, the best timer is time.clock()
	default_timer = time.clock
else:
	# On most other platforms the best timer is time.time()
	default_timer = time.time


class Return_home_request:
	def __init__(self, src_ip, file_name):
		self.src_ip = src_ip
		self.file_name = file_name
		self.request_time = int(default_timer())

	def is_expired(self):
		return int(default_timer()) - self.request_time > HOME_RETURN_REQUEST_TIMEOUT

class Download_request:
	def __init__(self, file_name, ):
		self.number_of_caught_packets = 0
		self.file_name = file_name
		self.received_payloads = [''] * MAX_NUMBER_OF_CHUNKS_PER_FILE

class Packet_data:
	def __init__(self, kind=None, src_ip=None, file_name=None, totoal_chunks=None):
		self.kind = kind
		self.src_ip = src_ip
		self.file_name = file_name
		self.total_chunks = totoal_chunks


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

class Network_drive(object):
	def __init__(self):
		self.ip = get_my_ip()
		self.ret_home_requests = []
		self.downloading_files = []
		self.packet = None

		self.print_start()

	#--------------------------------------------------------------------------

	def print_start(self):
		print("# Starting Network-Drive Node.")
		print("# Node ip: " + self.ip)

	def print_exit(self):
		print("# Shutting down Network-Drive Node.")

	#--------------------------------------------------------------------------

	def signal_handler(self, signum, frame):
		"""
		Handle print_exit via signals
		"""
		self.print_exit()
		msg = "\n(Terminated with signal %d)\n" % (signum)

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

	def get_random_src_dst(self):
		src = self.ip
		while (src == self.ip):
			src = "10.0.0." + str(randint(1, HOST_COUNT))
		
		dst = src
		while(dst == src or dst == self.ip):
			dst = "10.0.0." + str(randint(1, HOST_COUNT))

		return src, dst
			
	#--------------------------------------------------------------------------

	def get_socket(self):
		try: 
			current_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
			current_socket.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

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
		payload = PAYLOAD_DELIMITER.join([DATA_PAYLOAD_KEYWORD, self.ip, file_name, str(total_chunks)])
		payload = payload + PAYLOAD_DATA_BEGIN + data
		return payload

	def parse_payload(self, payload):
		parsed_payload = payload.split(PAYLOAD_DELIMITER)
		pd = Packet_data()
		pd.kind = parsed_payload[0]
		pd.src_ip = parsed_payload[1]
		pd.file_name = parsed_payload[2]

		if pd.kind == DATA_PAYLOAD_KEYWORD:
			idx = parsed_payload[3].find(PAYLOAD_DATA_BEGIN)
			pd.total_chunks = int(parsed_payload[3][:idx])
		self.packet = pd

	#--------------------------------------------------------------------------

	def collect_packet(self, downloading_obj, payload, icmp_id):
		if downloading_obj.received_payloads[int(icmp_id)] is not None:
			idx = payload.find(PAYLOAD_DATA_BEGIN)
			data = payload[idx + 1:]
			downloading_obj.number_of_caught_packets += 1
			downloading_obj.received_payloads[int(icmp_id)] = data
			if self.packet.total_chunks == downloading_obj.number_of_caught_packets:
				# save file to disk
				f= open(self.packet.file_name, "w+")
				for data in downloading_obj.received_payloads:
					if data == '':
						continue
					f.write(data)
				f.close()
				self.downloading_files.remove(downloading_obj)
				print "### file " + self.packet.file_name + " is saved."

	#--------------------------------------------------------------------------

	def download_file(self, file_name):
		self.downloading_files.append(Download_request(file_name))
		worker = threading.Thread(target=self.send_return_home_requests, args=(file_name, ))
		worker.start()

	def upload_file(self, filename):
		icmp_id = 0
		file_size = os.path.getsize(filename)
		total_chunks = file_size / PAYLOAD_SIZE
		if (file_size % PAYLOAD_SIZE) != 0:
			total_chunks += 1
		
		with open(filename, "r") as file:
			while True:
				data = file.read(PAYLOAD_SIZE)
				if data == '':
					break
				payload = self.generate_data_payload(filename, data, total_chunks)
				src, dst = self.get_random_src_dst()
				current_socket = self.get_socket()
				Network_drive.send_one_ping(current_socket, src, dst, icmp_id, payload)
				current_socket.close()
				icmp_id += 1
				time.sleep(SEND_DELAY_TIME)
				
	def send_return_home_requests(self, file_name):
		for i in range(1, HOST_COUNT + 1):
			dest_ip = "10.0.0." + str(i)
			if dest_ip == self.ip:
				continue

			current_socket = self.get_socket()
			payload = self.generate_return_home_payload(file_name)
			Network_drive.send_one_ping(current_socket, dest_ip, self.ip, 0, payload)
			print("# send retHome to " + dest_ip)
			current_socket.close()
			time.sleep(SEND_DELAY_TIME)

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
		for req_obj in self.ret_home_requests:
			if not req_obj.is_expired() and req_obj.file_name == file_name:
				return req_obj
		return None

	def check_if_packet_must_be_collected(self, file_name):
		for downloading_obj in self.downloading_files:
			if downloading_obj.file_name == file_name:
				return downloading_obj
		return None

	#--------------------------------------------------------------------------

	def run(self):
		self.setup_signal_handler()
		current_socket = self.get_socket()
		while True:
			if select.select([sys.stdin,],[],[],0.0)[0]:
				command = raw_input().split(' ')
				if command[0] == SEND_COMMAND_KEYWORD:
					worker = threading.Thread(target=self.upload_file, args=(command[1], ))
					worker.start()
				elif command[0] == GET_COMMAND_KEYWORD:
					self.download_file(command[1])
				elif command[0] == QUIT_COMMAND_KEYWORD:
					break
			
			delay = self.do(current_socket)
		current_socket.close()

	def do(self, current_socket):
		getPacket, icmp_header, payload = self.receive_one_ping(current_socket)

		if getPacket:
			self.parse_payload(payload)
			if self.packet.kind == HOME_RETURN_PAYLOAD_KEYWORD:
				# print("recieved home return: home_ip: " + self.packet.src_ip + ", file_name: " + self.packet.file_name)
				self.add_to_return_home_requests(
					src_ip=self.packet.src_ip,
					filename=self.packet.file_name
				)
			elif self.packet.kind == DATA_PAYLOAD_KEYWORD:
				downloading_obj = self.check_if_packet_must_be_collected(self.packet.file_name)
				req_obj = self.check_if_data_requested(self.packet.file_name)

				if downloading_obj:
						print("collecting packet, file_name: " + downloading_obj.file_name)
						self.collect_packet(downloading_obj, payload, icmp_header["packet_id"])
				elif req_obj:
					Network_drive.send_one_ping(current_socket, req_obj.src_ip, self.ip,
							icmp_header["packet_id"], payload)
					print("send packet to home: home_ip: " + req_obj.src_ip + ", file_name: " + req_obj.file_name)

				else:
					self.resend_ICMP(current_socket, icmp_header, payload)

	# send an ICMP ECHO_REQUEST packet
	@classmethod
	def send_one_ping(cls, current_socket, src, dst, icmp_packet_id, payload):
		# print("SEND : " + src[-1] + " -> " + dst[-1] + " Payload : " + payload)

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

	def resend_ICMP(self, current_socket, icmp_header, payload):
		src, dst = self.get_random_src_dst()
		Network_drive.send_one_ping(current_socket, src, dst, icmp_header["packet_id"], payload)

	def receive_one_ping(self, current_socket):
		timeout = 1
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

		icmpType = ""
		if (icmp_header["type"] != REPLY_TYPE):
			return False, None, None

		receive_time = default_timer()

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
		return True, icmp_header, packet_data[28:]

nd = Network_drive()
nd.run()
