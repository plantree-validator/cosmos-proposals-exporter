# Cosmos Chains Proposals Prometheus Exporter

This Prometheus exporter collects metrics about Cosmos chains proposals, focusing on active proposals that a specific validator has not voted on. The exporter can be configured to monitor multiple Cosmos chains.

## Configuration

Create a `config.yaml` file to configure the exporter. Below is an example configuration:

```yaml
chains:
  - name: likecoin
    node_url: https://mainnet-node.like.co
    validator_address: likevaloper********
  - name: osmosis
    node_url: https://lcd.osmosis.zone
    validator_address: osmovaloper******
# Scrape interval in seconds
scrape_interval: 600  
# Count of last proposals to check status 
scrape_last_proposals_count: 50
# Count of proposal voters to be searched in
voters_query_count: 200
