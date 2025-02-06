# proof_of_quality.py
import pandas as pd
import os
import logging
from typing import Dict, Any

points = {
    "REDDIT":50,
    "STEAM":50,
    "UBER":50,
    "LINKEDIN":50,
    "TWITCH":50,
    "AMAZON_PRIME":50,
    "NETFLIX":50,
    "ZOMATO":50,
    "SPOTIFY":50,
    "TWITTER":50,
}

def calculate_max_points(points_dict):
    return sum(points_dict.values())

def get_dynamic_task_score(uniqueness_count, task_type):
    max_point = points[task_type]

    if uniqueness_count >= 10:
        return max_point
    elif 5 <= uniqueness_count <= 9:
        return max_point * 0.5
    elif 1 <= uniqueness_count <= 4:
        return max_point * 0.1
    else:
        return 0

def calculate_browser_history_score(csv_path):
    df = pd.read_csv(csv_path)
    df['DateTime'] = pd.to_datetime(df['DateTime'])

    unique_rows = df.drop_duplicates(subset=['DateTime', 'NavigatedToUrl', 'PageTitle'])
    unique_count = len(unique_rows)
    base_score = 50

    if unique_count > 10000:
        uniqueness_score = base_score
    elif unique_count > 5000:
        uniqueness_score = 0.7 * base_score
    elif unique_count > 2000:
        uniqueness_score = 0.5 * base_score
    elif unique_count > 10:
        uniqueness_score = 0.05 * base_score
    else:
        uniqueness_score = 0

    max_date_diff = (df['DateTime'].max() - df['DateTime'].min()).days

    if max_date_diff > 180:
        date_range_score = 50
    elif 120 <= max_date_diff <= 180:
        date_range_score = 0.5 * 50
    else:
        date_range_score = 0

    total_score = int(uniqueness_score + date_range_score) / 2

    logging.info(f"Browser History Score: {total_score}")
    return total_score

def calculate_quality_score(input_data, config, unique_entry_details):
    """Calculate quality score based on contribution data and input files."""
    final_scores = {}
    total_secured_score = 0
    total_max_score = 0

    # Convert unique_entry_details into a dictionary for quick lookup
    logging.info(f"unique_entry_details is {unique_entry_details}")
    unique_entries_dict = {
    entry["type"]: {
        "unique_entry_count": entry["unique_entry_count"], 
        "type_unique_score": entry["type_unique_score"]
    }
        for entry in unique_entry_details
    }
    # Loop through each contribution in the input data
    for contribution in input_data['contribution']:
        task_type = contribution['type']
        securedSharedData = contribution['securedSharedData']
        type_unique_count = unique_entries_dict.get(task_type)["unique_entry_count"] # Get unique entries if available
        type_uniqueness_score = unique_entries_dict.get(task_type)["type_unique_score"] 

        if task_type in ['UBER', 'AMAZON_PRIME', 'ZOMATO', 'SPOTIFY', 'NETFLIX']:
            score = get_dynamic_task_score(type_unique_count, task_type)  # Use unique_entries instead of order_count
        elif task_type in ['REDDIT', 'STEAM', 'TWITCH',' TWITTER', 'LINKEDIN']:
            score = points[task_type] * type_uniqueness_score
        else:
            score = 0  # Default score for unknown types

        final_scores[task_type] = score
        total_secured_score += score

    # Check for CSV files starting with 'BrowserHistory' in the input directory
    csv_file = [f for f in os.listdir(config['input_dir']) if f.startswith("BrowserHistory") and f.endswith(".csv")]
    browser_history_score = 0
    if csv_file:
        csv_path = os.path.join(config['input_dir'], csv_file[0])
        browser_history_score = calculate_browser_history_score(csv_path)
        total_secured_score += browser_history_score
        total_max_score += 50

    total_max_score += calculate_max_points(points)

    # Normalize the total score
    normalized_total_score = total_secured_score / total_max_score if total_max_score > 0 else 0

    # Log the results
    logging.info(f"Total Secured Score: {total_secured_score}")
    logging.info(f"Total Max Score: {total_max_score}")
    logging.info(f"Normalized Total Score: {normalized_total_score}")

    return normalized_total_score
