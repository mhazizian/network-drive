from ping import Ping

p = Ping('10.0.0.0', '10.0.0.0', 1000, 3, 55)
ip_dst = '10.0.0.1'

current_socket = p.get_socket()
payload = p.generate_data_payload("test.txt", "salamsalamsalamsalamsalam", 2)

Ping.send_one_ping(current_socket, ip_dst, p.ip, 1, payload)

