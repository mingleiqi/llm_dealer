
from core.down_llms import is_socket_connected,check_proxy_running,download_all_files,github_token


if __name__ == "__main__":
    if github_token:
        print("GitHub token found. Using authenticated requests.")
    else:
        print("No GitHub token found. Using unauthenticated requests. Rate limits may apply.")
    
    proxy_host = "127.0.0.1"
    proxy_port = 10809
    if is_socket_connected(proxy_host, proxy_port):
        check_proxy_running(proxy_host, proxy_port, "http")
    
    download_all_files()