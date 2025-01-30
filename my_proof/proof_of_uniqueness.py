import hashlib
import redis
import hashlib
import json
import logging
import os
from urllib.parse import urlparse
import requests
import gnupg

# Connect to Redis
def get_redis_client():
    try:
        # TODO: For local testing comment this
        redis_client = redis.StrictRedis(
            host=os.environ.get('REDIS_HOST', None),
            port=os.environ.get('REDIS_PORT', None),
            db=0,
            password=os.environ.get('REDIS_PWD', None),
            decode_responses=True,
            socket_timeout=5,
            retry_on_timeout=True
        )
        # TODO: For local testing uncomment this
        # redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True) 
        redis_client.ping()
        return redis_client
    except redis.ConnectionError:
        return None

def hash_value(value):
    return hashlib.sha256(value.encode()).hexdigest() if isinstance(value, str) else hash_value(json.dumps(value))

# To extract taskSubType and securedSharedData from dataset shared
# This data will be used to store in Redis cache
def process_secured_data(contributions):
    processed = []
    for entry in contributions:
        sub_type = entry.get("taskSubType")
        secured_data = entry.get("securedSharedData")
        
        hashed_data = {key: {k: hash_value(v) for k, v in value.items()} if isinstance(value, dict) else hash_value(value) 
                       for key, value in secured_data.items()}
        
        processed.append({"subType": sub_type, "securedSharedData": hashed_data})
    return processed

def fetch_missing_files(files):
    downloaded_data = {}
    for file in files:
        file_id = file.get("file_id")
        file_url = file.get("file_url")
        try:
            response = requests.get(file_url)
            if response.status_code == 200:
                downloaded_data[file_id] = json.loads(response.text)
        except Exception as e:
            print(f"Failed to download {file_url}: {e}")
    return downloaded_data

def compare_secured_data(curr_data, new_data):
    result = []
    total_score = 0  # To calculate total normalized score
    
    # Convert curr_data to a dictionary for easier lookup
    curr_dict = {item["subType"]: item["securedSharedData"] for item in curr_data}
    
    # Iterate through new_data subTypes
    for new_item in new_data:
        sub_type = new_item.get("subType")
        new_secured_data = new_item.get("securedSharedData")
        
        if sub_type in curr_dict:
            curr_secured_data = curr_dict[sub_type]
            unique_hashes = set()
            total_hashes = set()
            
            # Compare fields inside securedSharedData
            for key, new_value in new_secured_data.items():
                curr_value = curr_secured_data.get(key, {})
                
                # If the value is a dict (like "orders" or "coins"), extract values
                if isinstance(new_value, dict):
                    new_hashes = set(new_value.values())
                    curr_hashes = set(curr_value.values()) if isinstance(curr_value, dict) else set()
                else:
                    new_hashes = {new_value}
                    curr_hashes = {curr_value} if curr_value else set()
                
                unique_hashes.update(curr_hashes - new_hashes)
                total_hashes.update(curr_hashes)
            
            # Calculate subtype unique score (avoid division by zero)
            subtype_unique_score = (len(unique_hashes) / len(total_hashes)) if total_hashes else 0
            total_score += subtype_unique_score  # Sum up scores
            
            # Add results
            result.append({
                "subType": sub_type,
                "unique_hashes_in_curr": len(unique_hashes),
                "total_hashes_in_curr": len(total_hashes),
                "subtype_unique_score": subtype_unique_score
            })

    # Calculate total normalized score
    total_normalized_score = total_score / len(result) if result else 0

    logging.info(f" result, normalised score{
        total_normalized_score
    }")
    
    return {
        "comparison_results": result,
        "total_normalized_score": total_normalized_score
    }

def download_file(file_url, save_path):
    response = requests.get(file_url, stream=True)
    response.raise_for_status()
    
    with open(save_path, 'wb') as file:
        for chunk in response.iter_content(chunk_size=8192):
            file.write(chunk)
    
    return save_path

def download_and_decrypt(file_url, signature):
    try:
        # Ensure the download folder exists
        download_folder = "./download"
        os.makedirs(download_folder, exist_ok=True)
        
        # Define paths
        encrypted_file_path = os.path.join(download_folder, "encrypted_file.gpg")
        decrypted_file_path = os.path.join(download_folder, "decrypted.json")
        
        # Initialize GPG instance
        gpg = gnupg.GPG()
        
        # Download the encrypted file
        download_file(file_url, encrypted_file_path)
        
        # Read encrypted content
        with open(encrypted_file_path, 'rb') as encrypted_file:
            encrypted_data = encrypted_file.read()
        
        # Decrypt the data
        decrypted_data = gpg.decrypt(encrypted_data, passphrase=signature)
        
        if not decrypted_data.ok:
            raise Exception(f"Decryption failed: {decrypted_data.stderr}")
        
        # Convert decrypted data to JSON and save it
        decrypted_json = json.loads(str(decrypted_data))
        with open(decrypted_file_path, 'w') as decrypted_file:
            json.dump(decrypted_json, decrypted_file, indent=2)
        
        print(f'Decryption successful, saved to {decrypted_file_path}')
        return decrypted_file_path
    except Exception as error:
        print(f"Error during decryption: {error}")
        raise


# TODO: call api to get {"file_id:"", "file_url":""}[]
def get_file_details_from_wallet_address(walletAddress):
    return None

def main(curr_file_id, curr_input_data, file_list):
    redis_client = get_redis_client()
    sign = "0x1195b3bd9821ff98e91a9ea92913cdfc1b2be36a72a8dfb7c220b5bf79e177a87547a3b2340bf1cbb73e48cc7b964be028348b55a0f4cd974eec4d4a5c06d5df1c"
    # file_url = "https://drive.google.com/uc?export=download&id=1unoDd1-DM6vwtdEpAdeUaVctossu_DhA"
    # download_and_decrypt(file_url, sign)
    processed_data = process_secured_data(curr_input_data.get("contribution", []))
    all_other_data = []

    if redis_client:
        for file in file_list:
            file_id = file.get("file_id")
            stored_data = redis_client.get(file_id)
            if stored_data:
                for entry in json.loads(stored_data):
                    all_other_data.append(entry)
            
    else:
       if file_list:
        download_folder = "./download"
        os.makedirs(download_folder, exist_ok=True)
        
        for file in file_list:
            file_url = file.get("file_url")
            if file_url:
                decrypted_path = download_and_decrypt(file_url, sign)
                if decrypted_path:
                    with open(decrypted_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # logging.info(f"{data["contribution"]}")
                        contribution_array = data["contribution"]
                        if isinstance(contribution_array, list):
                            for entry in contribution_array:
                                if isinstance(entry, dict):
                                    all_other_data.append(entry)
    
    if redis_client:
        redis_client.set(curr_file_id, json.dumps(processed_data))
    
     
    response = compare_secured_data(processed_data, all_other_data)

    # Return the processed data
    return {
        "avg_score": response["total_normalized_score"], 
        "result": response["comparison_results"] 
    }

# TODO: Modify for multiple file downloads
def calculate_uniqueness_score(curr_input_data):
    wallet_address = curr_input_data.get('walletAddress')
    # file_list = get_file_details_from_wallet_address(wallet_address) #TODO: add this later on
    file_list = [
        {"file_id": "3", "file_url":"https://drive.google.com/uc?export=download&id=1unoDd1-DM6vwtdEpAdeUaVctossu_DhA"}, 
        {"file_id": "", "file_url":""}, 
        {"file_id": "", "file_url":""}
    ]
    curr_file_id = os.environ.get('FILE_ID', "7") 
    result = main(curr_file_id, curr_input_data, file_list)
    return result


