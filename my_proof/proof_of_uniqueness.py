import hashlib
import zipfile
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
            port=os.environ.get('REDIS_PORT', 0),
            db=0,
            password=os.environ.get('REDIS_PWD', ""),
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

# To extract taskSubType and securedSharedData from the contribution field of dataset shared
# This data will be used for hashing as well as caching in Redis
def process_secured_data(contributions):
    processed = []
    for entry in contributions:
        sub_type = entry.get("taskSubType")
        secured_data = entry.get("securedSharedData")
        
        hashed_data = {
            key: (
                {k: hash_value(v) for k, v in value.items()} if isinstance(value, dict) else
                [hash_value(item) for item in value] if isinstance(value, list) else
                hash_value(value)
            )
            for key, value in secured_data.items()
        }

        processed.append({"subType": sub_type, "securedSharedData": hashed_data})
    return processed


def compare_secured_data(processed_curr_data: list, processed_old_data: list):
    result = []
    total_score = 0  # To calculate total normalized score

    # Convert processed_curr_data to a dictionary for easier lookup
    curr_dict = {item["subType"]: item["securedSharedData"] for item in processed_curr_data}
    old_dict = {item["subType"]: item["securedSharedData"] for item in processed_old_data}
    
    # Handle case where processed_old_data is empty
    if not processed_old_data:
        for sub_type, secured_data in curr_dict.items():
            total_hashes = set()
            
            for key, value in secured_data.items():
                if isinstance(value, dict):
                    total_hashes.update(value.values())
                elif isinstance(value, list):
                    total_hashes.update(value)
            
            result.append({
                "subType": sub_type,
                "unique_hashes_in_curr": len(total_hashes),
                "total_hashes_in_curr": len(total_hashes),
                "subtype_unique_score": 1.0
            })
            total_score += 1.0

        return {
            "comparison_results": result,
            "total_normalized_score": 1.0
        }
    
    # Iterate through processed_old_data subTypes
    logging.info(f"Processed old data {processed_old_data}")
    all_sub_types = set(curr_dict.keys()).union(set(old_dict.keys()))
    
    for sub_type in all_sub_types:
        curr_secured_data = curr_dict.get(sub_type, {})
        old_secured_data = old_dict.get(sub_type, {})
        unique_hashes = set()
        total_hashes = set()
        
        # If subType is only in curr_dict, consider all hashes unique
        if sub_type not in old_dict:
            for key, value in curr_secured_data.items():
                if isinstance(value, dict):
                    unique_hashes.update(value.values())
                    total_hashes.update(value.values())
                elif isinstance(value, list):
                    unique_hashes.update(value)
                    total_hashes.update(value)
            subtype_unique_score = 1.0
        else:
            # Compare fields inside securedSharedData
            for key, old_value in old_secured_data.items():
                curr_value = curr_secured_data.get(key, {})
                
                # Convert dict values to sets of hashes
                if isinstance(old_value, dict):
                    old_hashes = set(old_value.values())
                    curr_hashes = set(curr_value.values()) if isinstance(curr_value, dict) else set()
                
                # Convert list values to sets of hashes
                elif isinstance(old_value, list):
                    old_hashes = set(old_value)
                    curr_hashes = set(curr_value) if isinstance(curr_value, list) else set()
                
                unique_hashes.update(curr_hashes - old_hashes)
                total_hashes.update(curr_hashes)
            
            # Calculate subtype unique score (avoid division by zero)
            subtype_unique_score = (len(unique_hashes) / len(total_hashes)) if total_hashes else 0
        
        total_score += subtype_unique_score  # Sum up scores
        
        # Add results
        logging.info(f"sub_type: {sub_type}, unique_hashes_in_curr: {len(unique_hashes)}")
        result.append({
            "subType": sub_type,
            "unique_hashes_in_curr": len(unique_hashes),
            "total_hashes_in_curr": len(total_hashes),
            "subtype_unique_score": subtype_unique_score
        })

    # Calculate total normalized score
    total_normalized_score = total_score / len(result) if result else 0

    logging.info(f"Result, normalized score: {total_normalized_score}")
    
    return {
        "comparison_results": result,
        "total_normalized_score": total_normalized_score
    }

def get_unique_entries(comparison_results):
    """
    Extracts subType and unique entry count from comparison results.

    :param comparison_results: List of dictionaries containing comparison results
    :return: List of dictionaries with subType and unique entry count
    """
    return [
        {
            "subType": entry["subType"],
            "unique_entry_count": entry["unique_hashes_in_curr"],
            "subtype_unique_score": entry["subtype_unique_score"]
        }
        for entry in comparison_results
    ]

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
        decrypted_zip_path = os.path.join(download_folder, "decrypted.zip")
        extracted_folder = os.path.join(download_folder, "extracted")

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

        # Save decrypted output
        with open(decrypted_zip_path, 'wb') as decrypted_file:
            decrypted_file.write(decrypted_data.data)

        # Check if the decrypted file is a ZIP archive
        if zipfile.is_zipfile(decrypted_zip_path):
            os.makedirs(extracted_folder, exist_ok=True)

            with zipfile.ZipFile(decrypted_zip_path, 'r') as zip_ref:
                zip_ref.extractall(extracted_folder)
            
            # Find JSON file inside the extracted folder
            json_file = None
            for root, _, files in os.walk(extracted_folder):
                for file in files:
                    if file.endswith(".json"):
                        json_file = os.path.join(root, file)
                        break

            if json_file:
                print(f"Decryption successful, JSON extracted to {json_file}")
                return json_file
            else:
                raise Exception("No JSON file found inside the decrypted ZIP")
        else:
            # If the decrypted output is not a ZIP, assume it's JSON
            decrypted_json = json.loads(decrypted_data.data)
            with open(decrypted_file_path, 'w') as json_file:
                json.dump(decrypted_json, json_file, indent=2)

            print(f"Decryption successful, saved to {decrypted_file_path}")
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
    processed_curr_data = process_secured_data(curr_input_data.get("contribution", []))
    processed_old_data = []

    if redis_client:
        for file in file_list:
            file_id = file.get("file_id")
            stored_data = redis_client.get(file_id)
            if stored_data:
                for entry in json.loads(stored_data):
                    processed_old_data.append(entry)
            
    else:
        cnt = 0
        for file in file_list:
            file_url = file.get("file_url")
            if file_url:
                decrypted_data = download_and_decrypt(file_url, sign)
                cnt+=1
                logging.info(f"download called {cnt}")
                # Load data from the JSON file
                json_file_path = decrypted_data
                with open(json_file_path, 'r', encoding="utf-8") as json_file:
                    downloaded_data = json.load(json_file)
                # process and generate key values with respective hash values
                logging.info(f"downloaded_data is {downloaded_data.get("contribution")}")
                processed_old_data += process_secured_data(downloaded_data.get("contribution"))
    
    if redis_client:
        redis_client.set(curr_file_id, json.dumps(processed_curr_data))
    
     
    response = compare_secured_data(processed_curr_data, processed_old_data)

    # Return the processed data
    return {
        "avg_score": response["total_normalized_score"], 
        "result": response["comparison_results"] 
    }

# TODO: Modify for multiple file downloads
def uniqueness_helper(curr_input_data):
    wallet_address = curr_input_data.get('walletAddress')
    # file_list = get_file_details_from_wallet_address(wallet_address) #TODO: add this later on
    file_list = [
        {"file_id": "3", "file_url":"https://drive.google.com/uc?export=download&id=1unoDd1-DM6vwtdEpAdeUaVctossu_DhA"}, 
        {"file_id": "4", "file_url":"https://drive.usercontent.google.com/download?id=1RFugr1lIfnt8Rzuw0TQ9_6brzZEer2PZ&export=download&authuser=0"}, 
        # {"file_id": "5", "file_url":"https://drive.google.com/uc?export=download&id=1unoDd1-DM6vwtdEpAdeUaVctossu_DhA"},
        # {"file_id": "11", "file_url":"https://drive.usercontent.google.com/download?id=1RFugr1lIfnt8Rzuw0TQ9_6brzZEer2PZ&export=download&authuser=0"}, 
    ]
    curr_file_id = os.environ.get('FILE_ID', "9") 
    response = main(curr_file_id, curr_input_data, file_list)
    res = {
        "unique_entries": get_unique_entries(response.get("result")),
        "uniqueness_score": response.get("avg_score")
    }
    return res


