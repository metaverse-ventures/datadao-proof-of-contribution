import json
import logging
import os
from typing import Dict, Any
import requests
from jwt import encode as jwt_encode
import pandas as pd
from datetime import timedelta

from my_proof.models.proof_response import ProofResponse

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

# Contribution subtype weights
# CONTRIBUTION_SUBTYPE_WEIGHTS = {
#     # "YOUTUBE_HISTORY": 1.5,
#     # "YOUTUBE_PLAYLIST": 1.2,
#     # "YOUTUBE_SUBSCRIBERS": 1.3,
#     # "NETFLIX_HISTORY": 1.4,
#     # "NETFLIX_FAVORITE": 1.1,
#     # "SPOTIFY_PLAYLIST": 1.2,
#     # "SPOTIFY_HISTORY": 1.3,
#     # "AMAZON_PRIME_VIDEO": 1.4,
#     # "AMAZON_ORDER_HISTORY": 1.1,
#     # "TWITTER_USERINFO": 1.0,
#     # "FARCASTER_USERINFO": 1.1,

#     YOUTUBE_SUBSCRIBERS,
#     YOUTUBE_CHANNEL_DATA,
#     YOUTUBE_CREATOR_PLAYLIST
#     YOUTUBE_STUDIO

#     AMAZON_PRIME_VIDEO # anticipated
#     AMAZON_ORDER_HISTORY # have

#     SPOTIFY_PLAYLIST
#     SPOTIFY_HISTORY

#     NETFLIX_HISTORY      # have
#     NETFLIX_FAVORITE

#     TWITTER_USERINFO    # have

#     FARCASTER_USERINFO  # have

#     COINMARKETCAP_USER_WATCHLIST # have

#     LINKEDIN_USER_INFO   # have
#     TRIP_USER_DETAILS    # have
# }

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

                # jwt_token = self.generate_jwt_token() # TODO: Uncomment
                # contribution_score_result = self.calculate_contribution_score(input_data)
                
                proof_response_object['uniqueness'] = 1.0  # uniqueness is validated at the time of submission
                proof_response_object['quality'] = self.calculate_quality_score(input_data)
                proof_response_object['ownership'] = 1.0
                # proof_response_object['ownership'] = self.calculate_ownership_score(jwt_token, input_data) # TODO: Uncomment
                proof_response_object['authenticity'] = self.calculate_authenticity_score(input_data)

                if proof_response_object['authenticity'] < 1.0:
                    proof_response_object['valid'] = False

                # Calculate the final score
                proof_response_object['score'] = self.calculate_final_score(proof_response_object)

                proof_response_object['attributes'] = {
                    # 'normalizedContributionScore': contribution_score_result['normalized_dynamic_score'],
                    # 'totalContributionScore': contribution_score_result['total_dynamic_score'],
                }

        logging.info(f"Proof response: {proof_response_object}")
        return proof_response_object

    def generate_jwt_token(self):
        secret_key = self.config.get('jwt_secret_key', 'default_secret')
        expiration_time = self.config.get('jwt_expiration_time', 180)
        return jwt_encode({}, secret_key, algorithm='HS256')

    def calculate_contribution_score(self, data_list: Dict[str, Any]) -> Dict[str, float]:
        contributions = data_list.get('contribution', [])

        total_dynamic_score = 0
        for item in contributions:
            type_ = item.get('type')
            task_subtype = item.get('taskSubType')

            if type_ and task_subtype:
                base_score = TASK_DATA_TYPE_MAPPING.get(type_, {}).get(task_subtype, 0)
                weight = CONTRIBUTION_SUBTYPE_WEIGHTS.get(task_subtype, 1)
                total_dynamic_score += base_score * weight

        if len(contributions) > CONTRIBUTION_THRESHOLD:
            total_dynamic_score += EXTRA_POINTS

        max_possible_score = sum(
            base * CONTRIBUTION_SUBTYPE_WEIGHTS.get(subtype, 1)
            for type_, subtypes in TASK_DATA_TYPE_MAPPING.items()
            for subtype, base in subtypes.items()
        )

        normalized_dynamic_score = min(total_dynamic_score / max_possible_score, 1)

        return {
            'total_dynamic_score': total_dynamic_score,
            'normalized_dynamic_score': normalized_dynamic_score,
        }

    def calculate_authenticity_score(self, data_list: Dict[str, Any]) -> float:
        contributions = data_list.get('contribution', [])
        valid_domains = ["wss://witness.reclaimprotocol.org/ws", "reclaimprotocol.org"]

        valid_count = sum(
            1 for contribution in contributions
            if contribution.get('witnesses', '').endswith(tuple(valid_domains))
        )

        return round(valid_count / len(contributions), 5) if contributions else 0

    def calculate_ownership_score(self, jwt_token: str, data: Dict[str, Any]) -> float:
        # if not jwt_token or not isinstance(jwt_token, str):
        #     raise ValueError('JWT token is required and must be a string')
        # if not data or not isinstance(data, dict) or 'walletAddress' not in data or not isinstance(data.get('subType'), list):
        #     raise ValueError('Invalid data format. Ensure walletAddress is a string and subType is an array.')

        # try:
        #     headers = {
        #         'Authorization': f'Bearer {jwt_token}',  # Attach JWT token in the Authorization header
        #     }
        #     response = requests.post(self.config.get(validator_base_api_url), json=data, headers=headers)

        #     response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)

        #     # return response.json().get('success', False) and 1.0 or 0.0
            return 1.0
        # except requests.exceptions.RequestException as e:
        #     logging.error(f"Error during API request: {e}")
        #     return 0.0

        # except requests.exceptions.HTTPError as error:
        #     print({'error': error})
        #     if error.response.status_code == 400:
        #         return 0.0
        #     raise ValueError(f'API call failed: {error.response.json().get("error", str(error))}')


    def calculate_final_score(self, proof_response_object: Dict[str, Any]) -> float:
        attributes = ['authenticity', 'uniqueness', 'quality', 'ownership']

        valid_attributes = [
            proof_response_object.get(attr, 0) for attr in attributes
            if proof_response_object.get(attr) is not None
        ]

        if not valid_attributes:
            return 0

        return round(sum(valid_attributes) / len(valid_attributes), 5)


    # Calculate Quality Scoring Functions
    # Each function provides score that is out of 50

    # Scoring thresholds
    def get_watch_history_score(self, count, task_subtype):
        max_point = points[task_subtype]
        if count >= 10:
            return max_point
        elif 4 <= count <= 9:
            return max_point * 0.5
        elif 1 <= count <= 3:
            return max_point * 0.1
        else:
            return 0

    # Watch score calculation out of 50
    # Function to calculate score based on 15-day intervals using Pandas
    # 15 days interval is taken to prevent spamming of netflix history
    def calculate_watch_score(self, watch_data, task_subtype):
        # Convert the input data into a pandas DataFrame
        df = pd.DataFrame(watch_data)

        # Convert the 'date' column to datetime
        df['Date'] = pd.to_datetime(df['Date'], format='%Y-%m-%d')

        # Determine the start and end dates dynamically
        start_date = df['Date'].min()
        end_date = df['Date'].max()

        # Create 15-day intervals
        intervals = pd.date_range(start=start_date, end=end_date, freq='15D')

        # Count the number of shows watched in each interval
        interval_counts = []
        for i in range(len(intervals) - 1):
            interval_start = intervals[i]
            interval_end = intervals[i + 1]
            count = df[(df['Date'] >= interval_start) & (df['Date'] < interval_end)].shape[0]
            interval_counts.append(count)

        # Calculate the scores for each interval
        interval_scores = [get_watch_history_score(count, task_subtype) for count in interval_counts]

        # Calculate the overall score (average of interval scores)
        overall_score = sum
        (interval_scores) / len(interval_scores) if interval_scores else 0

        return overall_score, interval_scores


    def get_order_history_score(self, orderCount, task_subtype):
        # Assuming full score for 10 or more orders
        max_point = points[task_subtype]

        if orderCount >= 10:
            return max_point
        # Assuming half score for 5-9 orders
        elif 5 <= orderCount <= 9:
            return max_point * 0.5
        # Assuming 10% score for 1-4 orders
        elif 1 <= orderCount <= 4:
            return max_point * 0.1
        # Assuming 0 score for 0 orders
        else:
            return 0
    

    # Main function to calculate scores
    def calculate_quality_score(self, input_data):
        
        # Initialize a dictionary to store the final scores
        final_scores = {}
        total_secured_score = 0
        total_max_score = 0
        
        # Loop through each contribution in the input data
        for contribution in input_data['contribution']:

            task_subtype = contribution['taskSubType']
            securedSharedData = contribution['securedSharedData']
            
            # Can be used for AMAZON_PRIME_VIDEO
            if task_subtype == 'NETFLIX_HISTORY':
                # Just provide the required parameters securedSharedData['csv']
                score, interval_scores = calculate_watch_score(securedSharedData['csv'], task_subtype)
                final_scores[task_subtype] = score

            elif task_subtype in ['AMAZON_ORDER_HISTORY', 'TRIP_USER_DETAILS']:
                order_count = len(securedSharedData.get('orders', {}))
                if order_count == 0:
                    score = 0
                else:
                    # Just provide the required parameters order_count, task_subtype
                    score = self.get_order_history_score(order_count, task_subtype)
                final_scores[task_subtype] = score

            elif task_subtype in ['FARCASTER_USERINFO', 'TWITTER_USERINFO', 'LINKEDIN_USER_INFO']:
                score = points[task_subtype]
                final_scores[task_subtype] = score
            
            # Update total secured score and total max score
            total_secured_score += final_scores[task_subtype]
            total_max_score += points[task_subtype]
        
        # Calculate the normalized total score
        normalized_total_score = total_secured_score / total_max_score if total_max_score > 0 else 0
        
        return normalized_total_score