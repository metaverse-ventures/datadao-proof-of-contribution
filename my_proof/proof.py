import json
import logging
import os
from typing import Dict, Any
import requests
from jwt import encode as jwt_encode
import pandas as pd
import numpy as np
from typing import Any, List, Dict
from datetime import datetime, timedelta, timezone

from my_proof.proof_of_authenticity import calculate_authenticity_score
from my_proof.proof_of_ownership import calculate_ownership_score, generate_jwt_token
from my_proof.proof_of_quality import calculate_quality_n_type_score
from my_proof.proof_of_uniqueness import uniqueness_helper
from my_proof.models.proof_response import ProofResponse

# Ensure logging is configured
logging.basicConfig(level=logging.INFO)


CONTRIBUTION_THRESHOLD = 4
EXTRA_POINTS = 5

class Proof:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.proof_response = ProofResponse(dlp_id=config['dlp_id'])
        self.proof_response_object = {
            'dlp_id': self.config.get('dlp_id', '24'),
            'valid': True,
        }
        
    def generate(self) -> ProofResponse:
        """Generate proofs for all input files."""
        logging.info("Starting proof generation")

        for input_filename in os.listdir(self.config['input_dir']):
            input_file = os.path.join(self.config['input_dir'], input_filename)
            if os.path.splitext(input_file)[1].lower() == '.json':
                with open(input_file, 'r', encoding='utf-8') as f:
                    input_data = json.load(f)

                logging.info(f"Processing file: {input_filename}")
               
                # self.proof_response_object['ownership'] = 1.0
                wallet_w_types = self.extract_wallet_address_and_types(input_data) 
                self.proof_response_object['ownership'] = self.calculate_ownership_score(wallet_w_types)
                input_hash_details = uniqueness_helper(input_data)
                unique_entry_details = input_hash_details.get("unique_entries")
                self.proof_response_object['uniqueness'] = input_hash_details.get("uniqueness_score")
                self.proof_response_object['quality'] = self.calculate_quality_score(input_data, unique_entry_details)
                self.proof_response_object['authenticity'] = self.calculate_authenticity_score(input_data)

                if self.proof_response_object['authenticity'] < 1.0:
                    self.proof_response_object['valid'] = False

                # Calculate the final score
                self.proof_response_object['score'] = self.calculate_individual_scores(input_data, self.config, unique_entry_details, valid_domains=["reclaimprotocol.org"])
                # self.calculate_final_score(self.proof_response_object)

                # self.proof_response_object['attributes'] = {
                #     # 'normalizedContributionScore': contribution_score_result['normalized_dynamic_score'],
                #     # 'totalContributionScore': contribution_score_result['total_dynamic_score'],
                # }

        logging.info(f"Proof response: {self.proof_response_object}")
        return self.proof_response_object

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

    def extract_wallet_address_and_types(self, input_data):
        wallet_address = input_data.get('walletAddress')
        types = [contribution.get('type') for contribution in input_data.get('contributions', [])]
        return  {'walletAddress': wallet_address, 'types': types}

    def calculate_authenticity_score(self, input_data: Dict[str, Any]) -> float:
        """Calculate authenticity score."""
        contributions = input_data.get('contributions', [])
        valid_domains = ["wss://witness.reclaimprotocol.org/ws", "reclaimprotocol.org"]
        return calculate_authenticity_score(contributions, valid_domains)

    def calculate_ownership_score(self, input_data: Dict[str, Any]) -> float:
        """Calculate ownership score."""
        wallet_address = input_data.get('walletAddress')
        types = input_data.get('types', [])
        data = {
            'walletAddress': wallet_address,
            'types': types
        }
        
        jwt_token = generate_jwt_token(wallet_address, self.config.get('jwt_secret_key'), self.config.get('jwt_expiration_time', 16000))
        return calculate_ownership_score(jwt_token, data, self.config.get('validator_base_api_url'))
    
    def calculate_quality_score(self, input_data, unique_entries):
        return calculate_quality_n_type_score(input_data, self.config, unique_entries).get('quality_score', 0)
    
    def calculate_individual_scores(
        self,
        input_data: Dict[str, Any], 
        config: Dict[str, Any], 
        unique_entry_details: List[Dict[str, Any]], 
        valid_domains: List[str],
    ) -> Dict[str, Any]:
        """
        Compute individual quality, uniqueness, and authenticity scores for each contribution type.
        """
        # Calculate quality and uniqueness scores
        quality_results = calculate_quality_n_type_score(input_data, config, unique_entry_details)
        type_scores = quality_results["type_scores"]
        
        # Calculate authenticity scores
        authenticity_scores = {}
        for contribution in input_data['contributions']:
            task_type = contribution['type']
            witness_urls = contribution.get('witnesses', [])
            
            # Determine if any valid domain is present
            auth_score =  1 if any(domain in contribution.get('witnesses', '') for domain in valid_domains) else 0
            logging.info(f"Authenticity score for {task_type}: {auth_score}, with witness URLs: {witness_urls}")
            
            authenticity_scores[task_type] = auth_score
        
        # Combine scores
        final_scores = {}
        for task_type in type_scores.keys():
            final_scores[task_type] = {
                "type_points": type_scores[task_type]["type_points"],
                "quality_score": type_scores[task_type]["type_quality_score"],
                "uniqueness_score": type_scores[task_type]["type_uniqueness_score"],
                "authenticity_score": authenticity_scores.get(task_type, 0),
                "ownership_score": self.proof_response_object['ownership'],
                "individual_score": (type_scores[task_type]["type_quality_score"] + type_scores[task_type]["type_uniqueness_score"] + authenticity_scores.get(task_type, 0) + self.proof_response_object['ownership']) / 4
            }
        
        final_score = sum(score["individual_score"] for score in final_scores.values()) / len(final_scores)
        logging.info(f"Final Individual Scores: {final_scores}")
        return final_score
