from ping import Ping
import time
p = Ping('10.0.0.0', '10.0.0.0', 1000, 3, 55)

ip_dst = '10.0.0.1'
current_socket = p.get_socket()
payload = p.generate_data_payload("test.txt", "salam bar doostam gerami :DD", 2)
Ping.send_one_ping(current_socket, ip_dst, p.ip, 1, payload)
current_socket.close()

time.sleep(1)

current_socket = p.get_socket()
ip_dst = '10.0.0.1'
payload = p.generate_data_payload("test.txt", "khouuuuuubind?!! :))))", 2)
Ping.send_one_ping(current_socket, ip_dst, p.ip, 2, payload)
current_socket.close()

