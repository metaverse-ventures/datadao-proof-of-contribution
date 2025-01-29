import json
import logging
import os
from typing import Dict, Any
import requests
from jwt import encode as jwt_encode
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

from my_proof.proof_of_authenticity import calculate_authenticity_score
from my_proof.proof_of_ownership import calculate_ownership_score, generate_jwt_token
from my_proof.proof_of_quality import calculate_quality_score
from my_proof.proof_of_uniqueness import calculate_uniquness_score
from my_proof.models.proof_response import ProofResponse

# Ensure logging is configured
logging.basicConfig(level=logging.INFO)

# Task data type mapping with configurable points
TASK_DATA_TYPE_MAPPING = {
    "NETFLIX": {
        "NETFLIX_HISTORY": 50,
        "NETFLIX_FAVORITE": 50,
    },
    "SPOTIFY": {
        "SPOTIFY_PLAYLIST": 50,
        "SPOTIFY_HISTORY": 50,
    },
    "AMAZON": {
        "AMAZON_PRIME_VIDEO": 50,
        "AMAZON_ORDER_HISTORY": 50,
    },
    "TWITTER": {
        "TWITTER_USERINFO": 50,
    },
    "YOUTUBE": {
        "YOUTUBE_HISTORY": 50,
        "YOUTUBE_PLAYLIST": 50,
        "YOUTUBE_SUBSCRIBERS": 50,
    },
    "FARCASTER": {
        "FARCASTER_USERINFO": 50,
    },
}

points = {
    'YOUTUBE_SUBSCRIBERS': 50,
    'YOUTUBE_CHANNEL_DATA': 50,
    'YOUTUBE_CREATOR_PLAYLIST': 50,
    'YOUTUBE_STUDIO': 50,
    'AMAZON_PRIME_VIDEO': 50,
    'AMAZON_ORDER_HISTORY': 50,
    'SPOTIFY_PLAYLIST': 50,
    'SPOTIFY_HISTORY': 50,
    'NETFLIX_HISTORY': 50,
    'NETFLIX_FAVORITE': 50,
    'TWITTER_USERINFO': 50,
    'FARCASTER_USERINFO': 50,
    'COINMARKETCAP_USER_WATCHLIST': 50,
    'LINKEDIN_USER_INFO': 50,
    'TRIP_USER_DETAILS': 50
}

CONTRIBUTION_THRESHOLD = 4
EXTRA_POINTS = 5

class Proof:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.proof_response = ProofResponse(dlp_id=config['dlp_id'])

    def generate(self) -> ProofResponse:
        """Generate proofs for all input files."""
        logging.info("Starting proof generation")

        proof_response_object = {
            'dlp_id': self.config.get('dlp_id', '24'),
            'valid': True,
        }

        for input_filename in os.listdir(self.config['input_dir']):
            input_file = os.path.join(self.config['input_dir'], input_filename)
            if os.path.splitext(input_file)[1].lower() == '.json':
                with open(input_file, 'r', encoding='utf-8') as f:
                    input_data = json.load(f)

                logging.info(f"Processing file: {input_filename}")

                data = self.extract_wallet_address_and_subtypes(input_data) # TODO: Uncomment
                # jwt_token = generate_jwt_token(data['walletAddress'])# TODO: Uncomment
                # contribution_score_result = self.calculate_contribution_score(input_data)
                
                proof_response_object['uniqueness'] = calculate_uniquness_score(input_data)  # uniqueness is validated at the time of submission
                proof_response_object['quality'] = self.calculate_quality_score(input_data)
                # proof_response_object['ownership'] = 1.0
                proof_response_object['ownership'] = self.calculate_ownership(data) # TODO: Uncomment
                proof_response_object['authenticity'] = self.calculate_authenticity(input_data)

                if proof_response_object['authenticity'] < 1.0:
                    proof_response_object['valid'] = False

                # Calculate the final score
                proof_response_object['score'] = self.calculate_final_score(proof_response_object)

                # proof_response_object['attributes'] = {
                #     # 'normalizedContributionScore': contribution_score_result['normalized_dynamic_score'],
                #     # 'totalContributionScore': contribution_score_result['total_dynamic_score'],
                # }

        logging.info(f"Proof response: {proof_response_object}")
        return proof_response_object

    def generate_jwt_token(self, wallet_address):
        secret_key = self.config.get('jwt_secret_key', 'default_secret')
        expiration_time = self.config.get('jwt_expiration_time', 16000)  # Set to 10 minutes (600 seconds)
        
        # Set the expiration time to 10 minutes from now
        exp = datetime.now(timezone.utc) + timedelta(seconds=expiration_time)
        
        payload = {
            'exp': exp,
            'walletAddress': wallet_address  # Add wallet address to the payload
        }
        
        # Encode the JWT
        token = jwt_encode(payload, secret_key, algorithm='HS256')
        return token

    def extract_wallet_address_and_subtypes(self, input_data):
        wallet_address = input_data.get('walletAddress')
        subType = [contribution.get('taskSubType') for contribution in input_data.get('contribution', [])]
        return  {'walletAddress': wallet_address, 'subType': subType}
    
    def calculate_max_points(self, points_dict):
        return sum(points_dict.values())

    def calculate_ownership(self, input_data: Dict[str, Any]) -> float:
        """Calculate ownership score."""
        wallet_address = input_data.get('walletAddress')
        sub_types = input_data.get('contribution', [])
        data = {
            'walletAddress': wallet_address,
            'subType': [contribution.get('taskSubType') for contribution in sub_types]
        }
        
        jwt_token = generate_jwt_token(wallet_address, self.config.get('jwt_secret_key'), self.config.get('jwt_expiration_time', 16000))
        return calculate_ownership_score(jwt_token, data, self.config.get('validator_base_api_url'))

    def calculate_authenticity(self, input_data: Dict[str, Any]) -> float:
        """Calculate authenticity score."""
        contributions = input_data.get('contribution', [])
        valid_domains = ["wss://witness.reclaimprotocol.org/ws", "reclaimprotocol.org"]
        return calculate_authenticity_score(contributions, valid_domains)

    def calculate_final_score(self, proof_response_object: Dict[str, Any]) -> float:
        attributes = ['authenticity', 'uniqueness', 'quality', 'ownership']

        valid_attributes = [
            proof_response_object.get(attr, 0) for attr in attributes
            if proof_response_object.get(attr) is not None
        ]

        if not valid_attributes:
            return 0

        return sum(valid_attributes) / len(valid_attributes)
    
    def calculate_quality_score(self, input_data):
        return calculate_quality_score(input_data, self.config)

    # # Calculate Quality Scoring Functions
    # # Each function provides score that is out of 50

    # # Scoring thresholds
    # def get_watch_history_score(self, count, task_subtype):
    #     max_point = points[task_subtype]
    #     if count >= 10:
    #         return max_point
    #     elif 4 <= count <= 9:
    #         return max_point * 0.5
    #     elif 1 <= count <= 3:
    #         return max_point * 0.1
    #     else:
    #         return 0

    # # Watch score calculation out of 50
    # # Function to calculate score based on 15-day intervals using Pandas
    # # 15 days interval is taken to prevent spamming of netflix history
    # def calculate_watch_score(self, watch_data, task_subtype):
    #     # Convert the input data into a pandas DataFrame
    #     df = pd.DataFrame(watch_data)

    #     # Convert the 'date' column to datetime
    #     df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%y')

    #     # Determine the start and end dates dynamically
    #     start_date = df['Date'].min()
    #     end_date = df['Date'].max()

    #     # Create 15-day intervals
    #     intervals = pd.date_range(start=start_date, end=end_date, freq='15D')

    #     # Count the number of shows watched in each interval
    #     interval_counts = []
    #     for i in range(len(intervals) - 1):
    #         interval_start = intervals[i]
    #         interval_end = intervals[i + 1]
    #         count = df[(df['Date'] >= interval_start) & (df['Date'] < interval_end)].shape[0]
    #         interval_counts.append(count)

    #     # Calculate the scores for each interval
    #     interval_scores = [self.get_watch_history_score(count, task_subtype) for count in interval_counts]

    #     # Calculate the overall score (average of interval scores)
    #     overall_score = sum(interval_scores) / len(interval_scores) if interval_scores else 0

    #     return overall_score, interval_scores


    # def get_order_history_score(self, orderCount, task_subtype):
    #     # Assuming full score for 10 or more orders
    #     max_point = points[task_subtype]

    #     if orderCount >= 10:
    #         return max_point
    #     # Assuming half score for 5-9 orders
    #     elif 5 <= orderCount <= 9:
    #         return max_point * 0.5
    #     # Assuming 10% score for 1-4 orders
    #     elif 1 <= orderCount <= 4:
    #         return max_point * 0.1
    #     # Assuming 0 score for 0 orders
    #     else:
    #         return 0
    
    # def get_coins_pairs_score(self, coins_count, pairs_count, task_subtype):
    #     max_point = points[task_subtype]
    #     total_count = coins_count + pairs_count
        
    #     if total_count >= 10:
    #         return max_point
    #     elif 4 <= total_count <= 9:
    #         return max_point * 0.5
    #     elif 1 <= total_count <= 3:
    #         return max_point * 0.1
    #     else:
    #         return 0
    
    # # Max point 50 is used in code
    # def calculate_browser_history_score(self, csv_path):
    #     # Read CSV
    #     df = pd.read_csv(csv_path)
        
    #     # Convert DateTime column to datetime type
    #     df['DateTime'] = pd.to_datetime(df['DateTime'])
        
    #     # Identify unique rows based on (DateTime, NavigatedToUrl, PageTitle)
    #     unique_rows = df.drop_duplicates(subset=['DateTime', 'NavigatedToUrl', 'PageTitle'])
    #     unique_count = len(unique_rows)
    #     base_score = 50

    #     # Scoring based on unique data count
    #     if unique_count > 10000:
    #         uniqueness_score = base_score  # Full points if unique data is more than 10000
    #     elif unique_count > 5000:
    #         uniqueness_score = 0.7 * base_score  # 70% of full points for 5000-10000 unique entries
    #     elif unique_count > 2000:
    #         uniqueness_score = 0.5 * base_score  # 50% of full points for 2000-5000 unique entries
    #     elif unique_count > 10:
    #         uniqueness_score = 0.05 * base_score  # 5% of full points if unique data is 10 or less
    #     else:
    #         uniqueness_score = 0
        
    #     # Calculate the maximum DateTime difference
    #     max_date_diff = (df['DateTime'].max() - df['DateTime'].min()).days
        
    #     # Scoring based on date range
    #     if max_date_diff > 180:
    #         date_range_score = 50  # Full points for data spanning over 180 days
    #     elif 120 <= max_date_diff <= 180:
    #         date_range_score = 0.5 * 50  # Half points for data spanning 120-180 days
    #     else:
    #         date_range_score = 0  # No points for data within 120 days

    #     # Final score out of 100
    #     total_score = int(uniqueness_score + date_range_score)/2
        
    #     logging.info(f"Browser History Score: {total_score}") 
    #     return total_score


    # # Main function to calculate scores
    # def calculate_quality_score(self, input_data):
        
    #     # Initialize a dictionary to store the final scores
    #     final_scores = {}
    #     total_secured_score = 0
    #     total_max_score = 0
        
    #     # Loop through each contribution in the input data
    #     for contribution in input_data['contribution']:

    #         task_subtype = contribution['taskSubType']
    #         securedSharedData = contribution['securedSharedData']
            
    #         # Can be used for AMAZON_PRIME_VIDEO
    #         if task_subtype == 'NETFLIX_HISTORY':
    #             # Just provide the required parameters securedSharedData['csv']
    #             score, interval_scores = self.calculate_watch_score(securedSharedData['csv'], task_subtype)
    #             final_scores[task_subtype] = score

    #         elif task_subtype == 'COINMARKETCAP_USER_WATCHLIST':
    #             coins_count = len(securedSharedData.get('coins', {}))
    #             pairs_count = len(securedSharedData.get('pairs', {}))
    #             # Just provide the required parameters coins_count, pairs_count, task_subtype
    #             score = self.get_coins_pairs_score(coins_count, pairs_count, task_subtype)
    #             final_scores[task_subtype] = score

    #         elif task_subtype in ['AMAZON_ORDER_HISTORY', 'TRIP_USER_DETAILS']:
    #             order_count = len(securedSharedData.get('orders', {}))
    #             if order_count == 0:
    #                 score = 0
    #             else:
    #                 # Just provide the required parameters order_count, task_subtype
    #                 score = self.get_order_history_score(order_count, task_subtype)
    #             final_scores[task_subtype] = score

    #         elif task_subtype in ['FARCASTER_USERINFO', 'TWITTER_USERINFO', 'LINKEDIN_USER_INFO']:
    #             score = points[task_subtype]
    #             final_scores[task_subtype] = score
            
    #         # Update total secured score and total max score
    #         total_secured_score += final_scores[task_subtype]

    #     # Check for CSV files starting with 'BrowserHistory' in the input directory
    #     csv_file = [f for f in os.listdir(self.config['input_dir']) if f.startswith("BrowserHistory") and f.endswith(".csv")]  # Use self.config['input_dir'] here
        
    #     browser_history_score = 0
    #     # If there's at least one CSV file, check its length
    #     if csv_file:
    #         csv_path = os.path.join(self.config['input_dir'], csv_file[0])  # Use self.config['input_dir'] here
    #         browser_history_score = self.calculate_browser_history_score(csv_path)
    #         total_secured_score += browser_history_score
    #         total_max_score += 50

    #     total_max_score += self.calculate_max_points(points)   

    #     # Calculate the normalized total score
    #     normalized_total_score = total_secured_score / total_max_score if total_max_score > 0 else 0

    #     # Log the total secured score and total max score
    #     logging.info(f"Total Secured Score: {total_secured_score}")
    #     logging.info(f"Total Max Score: {total_max_score}")
    #     logging.info(f"Normalized Total Score: {normalized_total_score}")
        
    #     return normalized_total_score
