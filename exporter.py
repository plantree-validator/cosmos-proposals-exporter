import yaml
import requests
from prometheus_client import start_http_server, Gauge, Info, REGISTRY, PROCESS_COLLECTOR, PLATFORM_COLLECTOR, GC_COLLECTOR
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


PROPOSALS_ENDPOINT = "/cosmos/gov/v1/proposals?pagination.reverse=true&pagination.limit={scrape_proposals_count}&pagination.count_total=true"
VOTES_ENDPOINT = "/cosmos/gov/v1beta1/proposals/{proposal_id}/votes/{chain_address}"

# Retry settings
MAX_RETRIES = 5
RETRY_WAIT_TIME = 1  # in seconds

# Prometheus metrics
not_voted_gauge = Gauge('address_not_voted_on_proposals_count', 'Number of active proposals the address has not voted on', ['chain', 'alias'])
not_voted_info = Info('address_not_voted_on_proposal', 'Details of active proposals the address has not voted on', ['chain', 'alias', 'chain_address', 'proposal_id'])

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

def fetch_vote(node_url, proposal_id, chain_address):
    retries = 0
    while retries < MAX_RETRIES:
        try:
            url = node_url + VOTES_ENDPOINT.format(proposal_id=proposal_id, chain_address=chain_address)
            logger.info(f"Fetching vote from {url}")
            response = requests.get(url)
            response.raise_for_status()
            vote_response = response.json()
            
            if 'vote' in vote_response:
                vote_option = vote_response['vote']['options'][0]['option']
                logger.info(f"Vote found for proposal {proposal_id}. Voter: {chain_address}, Option: {vote_option}")
            return vote_response
        except requests.HTTPError as e:
            if response.status_code == 429:
                logger.warning(f"Rate limit exceeded. Retrying in {RETRY_WAIT_TIME} seconds...")
                time.sleep(RETRY_WAIT_TIME)
                retries += 1
                continue
            elif response.status_code == 400:
                vote_response = response.json()
                if vote_response.get('code') == 3:
                    logger.info(f"No vote found for proposal {proposal_id} by address {chain_address} (code 3)")
                    return None
            logger.error(f"Error fetching vote: {e}")
            return None
        except requests.RequestException as e:
            logger.error(f"Error fetching vote: {e}")
            return None
    logger.error(f"Max retries reached. Could not fetch vote for proposal {proposal_id}")
    return None

def is_proposal_active(proposal):
    now = datetime.now(timezone.utc)
    voting_start = date_parser.parse(proposal['voting_start_time']).replace(tzinfo=timezone.utc)
    voting_end = date_parser.parse(proposal['voting_end_time']).replace(tzinfo=timezone.utc)
    return voting_start <= now <= voting_end

def check_not_voted_proposals(chain):
    node_url = chain['node_url']
    chain_address = chain['chain_address']
    chain_name = chain['name']
    chain_alias = chain['alias']
    
    proposals = fetch_proposals(node_url)
    not_voted_proposals = []

    for proposal in proposals:
        if not is_proposal_active(proposal):
            continue
        proposal_id = proposal['id']
        proposal_title = proposal['title']
        vote = fetch_vote(node_url, proposal_id, chain_address)
        if vote is None or vote.get('code') == 3:
            not_voted_proposals.append({
                'id': proposal_id,
                'title': proposal_title
            })

    not_voted_gauge.labels(chain=chain_name, alias=chain_alias).set(len(not_voted_proposals))
    for proposal in not_voted_proposals:
        not_voted_info.labels(chain=chain_name, alias=chain_alias, chain_address=chain_address, proposal_id=proposal['id']).info({
            'proposal_title': proposal['title']
        })

def main():
    # Disable default Prometheus metrics
    REGISTRY.unregister(PROCESS_COLLECTOR)
    REGISTRY.unregister(PLATFORM_COLLECTOR)
    REGISTRY.unregister(GC_COLLECTOR)

    start_http_server(8000)
    while True:
        for chain in CHAINS:
            check_not_voted_proposals(chain)
        time.sleep(SCRAPE_INTERVAL)

if __name__ == "__main__":
    main()
