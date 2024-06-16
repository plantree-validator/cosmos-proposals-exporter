import yaml
import requests
from prometheus_client import start_http_server, Gauge, Info, REGISTRY
import time
import logging
from datetime import datetime, timezone
from dateutil import parser as date_parser

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration from file
with open('config.yaml') as config_file:
    config = yaml.safe_load(config_file)

CHAINS = config.get('chains', [])
SCRAPE_INTERVAL = config.get('scrape_interval', 60)
SCRAPE_PROPOSALS_COUNT = config.get('scrape_last_proposals_count', 50)
VOTERS_QUERY_COUNT = config.get('voters_query_count', 200)


PROPOSALS_ENDPOINT = "/cosmos/gov/v1/proposals?pagination.reverse=true&pagination.limit={scrape_proposals_count}&pagination.count_total=true"
VOTES_ENDPOINT = "/cosmos/gov/v1beta1/proposals/{proposal_id}/votes?pagination.limit={voters_query_count}"

# Prometheus metrics
not_voted_gauge = Gauge('validator_not_voted_on_proposals_count', 'Number of active proposals the validator has not voted on', ['chain'])
not_voted_info = Info('validator_not_voted_on_proposal', 'Details of active proposals the validator has not voted on', ['chain', 'proposal_id'])

def fetch_proposals(node_url):
    try:
        prop_url = node_url + PROPOSALS_ENDPOINT.format(scrape_proposals_count=SCRAPE_PROPOSALS_COUNT)
        logger.info(f"Fetching proposals from {prop_url}")
        response = requests.get(prop_url)
        response.raise_for_status()
        proposals = response.json().get('proposals', [])
        logger.info(f"Fetched {len(proposals)} proposals")
        return proposals
    except requests.RequestException as e:
        logger.error(f"Error fetching proposals: {e}")
        return []

def fetch_votes(node_url, proposal_id):
    try:
        url = node_url + VOTES_ENDPOINT.format(proposal_id=proposal_id,voters_query_count=VOTERS_QUERY_COUNT)
        logger.info(f"Fetching votes from {url}")
        response = requests.get(url)
        response.raise_for_status()
        votes = response.json().get('votes', [])
        logger.info(f"Fetched {len(votes)} votes for proposal {proposal_id}")
        return votes
    except requests.RequestException as e:
        logger.error(f"Error fetching votes: {e}")
        return []

def is_proposal_active(proposal):
    now = datetime.now(timezone.utc)
    voting_start = date_parser.parse(proposal['voting_start_time']).replace(tzinfo=timezone.utc)
    voting_end = date_parser.parse(proposal['voting_end_time']).replace(tzinfo=timezone.utc)
    return voting_start <= now <= voting_end

def check_not_voted_proposals(chain):
    node_url = chain['node_url']
    validator_address = chain['validator_address']
    chain_name = chain['name']
    
    proposals = fetch_proposals(node_url)
    not_voted_proposals = []

    for proposal in proposals:
        if not is_proposal_active(proposal):
            continue
        proposal_id = proposal['id']
        proposal_title = proposal['title']
        votes = fetch_votes(node_url, proposal_id)
        if not any(vote['voter'] == validator_address for vote in votes):
            not_voted_proposals.append({
                'id': proposal_id,
                'title': proposal_title
            })

    not_voted_gauge.labels(chain=chain_name).set(len(not_voted_proposals))
    for proposal in not_voted_proposals:
        not_voted_info.labels(chain=chain_name, proposal_id=proposal['id']).info({
            'proposal_title': proposal['title']
        })

def main():
    # Disable default Prometheus metrics
    for collector in list(REGISTRY._collector_to_names.keys()):
        REGISTRY.unregister(collector)

    start_http_server(8000)
    while True:
        for chain in CHAINS:
            check_not_voted_proposals(chain)
        time.sleep(SCRAPE_INTERVAL)

if __name__ == "__main__":
    main()
