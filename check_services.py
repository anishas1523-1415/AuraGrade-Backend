import socket
def check_port(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect(('127.0.0.1', port))
        return True
    except:
        return False
    finally:
        s.close()

if check_port(8000):
    print("Backend (8000) is UP")
else:
    print("Backend (8000) is DOWN")

if check_port(3000):
    print("Frontend (3000) is UP")
else:
    print("Frontend (3000) is DOWN")
