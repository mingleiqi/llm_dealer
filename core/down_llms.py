import os
import socket
import requests
import time
from datetime import datetime
import configparser
import json
import concurrent.futures

# GitHub repository details
owner = "wxy2ab"
repo = "akinterpreter"
branch = "main"

# Paths for different types of files
path_llms = "core/llms"

# List of individual files to download
files_to_download = [
    "core/utils/__init__.py",
    "core/utils/config_setting.py",
    "core/utils/log.py",
    "core/utils/retry.py",
    "core/utils/single_ton.py",
    "core/utils/timer.py",
    "core/utils/handle_max_tokens.py",
    "core/interpreter/__init__.py",
    "core/interpreter/ast_code_runner.py",
    "core/interpreter/data_summarizer.py",

]

def get_github_token():
    config = configparser.ConfigParser()
    try:
        config.read('setting.ini')
        return config.get('GitHub', 'token', fallback=None)
    except:
        return None

github_token = get_github_token()

def github_request(url, params=None, max_retries=3, delay=5):
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            remaining = response.headers.get('X-RateLimit-Remaining')
            if remaining:
                print(f"Remaining API calls: {remaining}")
            return response
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt + 1 < max_retries:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"Failed after {max_retries} attempts.")
                return None

def get_file_sha(owner, repo, path, branch):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    params = {"ref": branch}
    response = github_request(url, params)
    if response and response.status_code == 200:
        content = response.json()
        return content.get('sha')
    return None

def download_file(file_info, local_base_path="."):
    file_path = file_info['path']
    file_sha = file_info['sha']
    url = file_info['download_url']
    local_path = os.path.join(local_base_path, file_path)

    # Create local directory if it does not exist
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    # Check if file needs updating
    if os.path.exists(local_path):
        with open(local_path, 'rb') as f:
            import hashlib
            local_sha = hashlib.sha1(f.read()).hexdigest()
        if local_sha == file_sha:
            print(f"Skipping {local_path}: File is up to date")
            return

    response = github_request(url)
    if response and response.status_code == 200:
        with open(local_path, 'wb') as file:
            file.write(response.content)
        print(f"Downloaded: {local_path}")
    else:
        print(f"Failed to download: {local_path}")

def down_llms(path, local_base_path="."):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    params = {"ref": branch}
    response = github_request(url, params)
    if response and response.status_code == 200:
        files = response.json()
        print(f"Found {len(files)} files in {path}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(download_file, file_info, local_base_path) 
                       for file_info in files if file_info["type"] == "file"]
            concurrent.futures.wait(futures)
        
        print(f"Finished processing {path}")
    else:
        print(f"Failed to fetch file list from GitHub for path: {path}")
        if response:
            print(f"Status code: {response.status_code}")
            print(f"Response content: {response.text}")
        else:
            print("No response received from GitHub API")

def is_socket_connected(host, port):
    try:
        with socket.create_connection((host, port), timeout=5):
            return True
    except (socket.timeout, ConnectionRefusedError):
        return False

def check_proxy_running(host, port=10808, proxy_type="socks5"):
    try:
        if is_socket_connected(host, port):
            os.environ["http_proxy"] = f"{proxy_type}://{host}:{port}"
            os.environ["https_proxy"] = f"{proxy_type}://{host}:{port}"
            print(f"Connected to proxy: {proxy_type}://{host}:{port}")
        else:
            print("No proxy server found")
    except Exception as e:
        host = "127.0.0.1"
        os.environ["http_proxy"] = f"{proxy_type}://{host}:10808"
        os.environ["https_proxy"] = f"{proxy_type}://{host}:10808"
        print(f"Connected to default proxy: {proxy_type}://{host}:10808")

def download_all_files(local_base_path="."):
    # Download files from specific directories
    for path in [path_llms]:
        print(f"Downloading files from {path}")
        down_llms(path, local_base_path)

    # Download individual files
    for file_path in files_to_download:
        file_info = {
            'path': file_path,
            'sha': get_file_sha(owner, repo, file_path, branch),
            'download_url': f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
        }
        download_file(file_info, local_base_path)

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