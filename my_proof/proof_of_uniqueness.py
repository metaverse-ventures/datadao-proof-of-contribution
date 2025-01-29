import hashlib
import json
import os
import redis

# Connect to Redis
redis_client = redis.StrictRedis(
    host=os.environ.get('REDIS_HOST', None),
    port=os.environ.get('REDIS_PORT', None),
    db=0,
    password=os.environ.get('REDIS_PWD', None),
    decode_responses=True,
    socket_timeout=5,
    retry_on_timeout=True
)

def hash_secured_data(data: dict) -> str:
    """
    Creates a SHA-256 hash of the securedSharedData dictionary.

    :param data: Dictionary to be hashed.
    :return: Hexadecimal hash string.
    """
    json_data = json.dumps(data, sort_keys=True)  # Convert to sorted JSON string
    return hashlib.sha256(json_data.encode()).hexdigest()

def store_hash(subtype: str, hash_value: str) -> int:
    """
    Efficiently checks if the hash is present in Redis storage for a given subtype.
    If present, return 0. If not, store the hash in both a set (for quick lookups)
    and a list (to maintain order) and return 1.

    :param subtype: The category under which the hash is stored.
    :param hash_value: The hash to check and store.
    :return: 1 if the hash was added, 0 if it already existed.
    """
    list_key = f"subtype:list:{subtype}"  # List to maintain insertion order
    set_key = f"subtype:set:{subtype}"  # Set for quick existence check

    with redis_client.pipeline() as pipe:
        pipe.sismember(set_key, hash_value)
        exists = pipe.execute()[0]
    
    if exists:  # If hash exists in the set
        return 0.0  

    with redis_client.pipeline() as pipe:
        pipe.rpush(list_key, hash_value)  # Append to list
        pipe.sadd(set_key, hash_value)  # Add to set
        pipe.execute()
    
    return 1.0  # Hash was added

def calculate_uniquness_score(contribution_data: dict) -> float:
    """
    Processes all taskSubTypes in the contribution list.
    Hashes and stores each entry’s securedSharedData in Redis.
    Returns the mean of results (1 if added, 0 if already existed).

    :param contribution_data: JSON object containing contributions.
    :return: Mean of stored hash results.
    """
    results = []

    for entry in contribution_data.get("contribution", []):
        subtype = entry.get("taskSubType")
        secured_data = entry.get("securedSharedData")

        if subtype and secured_data:
            hash_value = hash_secured_data(secured_data)
            result = store_hash(subtype, hash_value)
            results.append(result)
            print(f"Subtype: {subtype}, Stored Hash: {hash_value} -> Result: {result}")

    return sum(results) / len(results)

# # Example usage
# if __name__ == "__main__":
#     input_data = {
#         "walletAddress": "0x1059Ed65AD58ffc83642C9Be3f24C250905a28F5",
#         "claimDate": "2025-01-07T07:57:30.883Z",
#         "contribution": [
#             {
#                 "type": "TWITTER",
#                 "taskSubType": "TWITTER_USERINFO",
#                 "claimedDate": "2025-01-07T07:04:15.421Z",
#                 "witnesses": "wss://witness.doom.org/ws",
#                 "walletAddress": "0x1059Ed65AD58ffc83642C9Be3f24C250905a28FB",
#                 "AccoundUsername": "username",
#                 "securedSharedData": {
#                     "userName": "username",
#                     "followers": "0",
#                     "following": "6",
#                     "posts": "0",
#                     "userDescription": None
#                 }
#             },
#             {
#                 "type": "AMAZON",
#                 "taskSubType": "AMAZON_ORDER_HISTORY",
#                 "claimedDate": "2025-01-07T07:02:48.887Z",
#                 "witnesses": "wss://witness.reclaimprotocol.org/ws",
#                 "walletAddress": "0x1059Ed65AD58ffc83642C9Be3f24C250905a28F5",
#                 "securedSharedData": {
#                     "orders": {
#                         "0": "boAt Airdopes 121 Pro Plus Truly Wireless in Ear Ear Buds",
#                         "1": "Gita Press हनुमानबाहुक (Hanuman Bahuk)"
#                     },
#                     "orderCount": 2
#                 }
#             }
#         ]
#     }

#     mean_result = process_contributions(input_data)
#     print(f"\nFinal Mean Result: {mean_result}")
