from ping import Ping

ip_dst = '10.0.0.1'
p = Ping('10.0.0.1', '10.0.0.2', 1000, 3, 55)

current_socket = p.get_socket()
payload = p.generate_data_payload("test.txt", "salamsalamsalamsalamsalam", 2)

Ping.send_one_ping(current_socket, p.ip, ip_dst, 1, payload)

