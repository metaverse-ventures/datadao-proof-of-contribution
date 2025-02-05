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
from my_proof.proof_of_uniqueness import uniqueness_helper
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

                
                # jwt_token = generate_jwt_token(data['walletAddress'])# TODO: Remove in future since generated inside calculate_ownership_score
                # proof_response_object['ownership'] = 1.0
                wallet_w_subTypes = self.extract_wallet_address_and_subtypes(input_data) # TODO: Uncomment
                proof_response_object['ownership'] = self.calculate_ownership_score(wallet_w_subTypes) # TODO: Uncomment
                input_hash_details = uniqueness_helper(input_data)
                unique_entry_details = input_hash_details.get("unique_entries")
                proof_response_object['uniqueness'] = input_hash_details.get("uniqueness_score")
                
                proof_response_object['quality'] = self.calculate_quality_score(input_data, unique_entry_details)
                proof_response_object['authenticity'] = self.calculate_authenticity_score(input_data)

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

    def calculate_authenticity_score(self, input_data: Dict[str, Any]) -> float:
        """Calculate authenticity score."""
        contributions = input_data.get('contribution', [])
        valid_domains = ["wss://witness.reclaimprotocol.org/ws", "reclaimprotocol.org"]
        return calculate_authenticity_score(contributions, valid_domains)

    def calculate_ownership_score(self, input_data: Dict[str, Any]) -> float:
        """Calculate ownership score."""
        wallet_address = input_data.get('walletAddress')
        sub_types = input_data.get('subType', [])
        data = {
            'walletAddress': wallet_address,
            'subType': sub_types
        }
        
        jwt_token = generate_jwt_token(wallet_address, self.config.get('jwt_secret_key'), self.config.get('jwt_expiration_time', 16000))
        return calculate_ownership_score(jwt_token, data, self.config.get('validator_base_api_url'))
    
    def calculate_quality_score(self, input_data, unique_entries):
        return calculate_quality_score(input_data, self.config, unique_entries)
    
    # def calculate_uniquness_score(self, input_data):
    #     return calculate_uniquness_score(input_data)
    
    def calculate_final_score(self, proof_response_object: Dict[str, Any]) -> float:
        attributes = ['authenticity', 'uniqueness', 'quality', 'ownership']
        weights = {
            'authenticity': 0.004,  # Low weight for authenticity
            'ownership': 0.006,  # Slightly higher than authenticity
            'quality': 0.395,  # Moderate weight for quality
            'uniqueness': 0.555  # High weight for uniqueness
        }

        weighted_sum = 0.0
        for attr in attributes:
            weighted_sum += proof_response_object.get(attr, 0) * weights[attr]

        return weighted_sum