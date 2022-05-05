from flask import Flask
import requests
import json
import sys #for printing to console in Flask
import time
from web3 import Web3
from constants import *

app = Flask(__name__)
w3 = Web3(Web3.HTTPProvider('https://mainnet.aurora.dev'))
brl_chef = w3.eth.contract(w3.toChecksumAddress(BRL_CHEF_ADDRESS), abi=BRL_CHEF_ABI)

@app.route("/")
def near_weth_apr_route():
    return {"auroraswap_near_weth_apr": calculate_apr(w3, brl_chef)};
  
  
def to_pool_info(pool):
    return {
        "address":pool[0],
        "allocPoint":pool[1],
        "lastRewardBlock":pool[2], #TODOs
        "accBRLPerShare":pool[3],
        "depositFeeBP":pool[4],
    }

def get_json_from_api(url):
    response = requests.get(url);
    json_data = json.loads(response.content)
    return json_data
    
def get_token_prices(list_of_tokens):
    addresses = ','.join(list_of_tokens)
    url = f"https://api.coingecko.com/api/v3/simple/token_price/aurora?contract_addresses={addresses}&vs_currencies=usd"
    return get_json_from_api(url)
    
def get_lp_staked(token, address, decimals):
    url = f"https://api.aurorascan.dev/api?module=account&action=tokenbalance&contractaddress={token}&address={address}&tag=latest&apikey={AURORASCAN_API_TOKEN}"
    return float(get_json_from_api(url)["result"])/decimals
    
def get_lp_supply(address, decimals):
    url = f"https://api.aurorascan.dev/api?module=stats&action=tokensupply&contractaddress={address}&apikey={AURORASCAN_API_TOKEN}"
    return float(get_json_from_api(url)["result"])/decimals
  
def get_gwei_balance_of_token_for_address(w3, token, address):
    get_balance_abi = '[{"inputs": [{ "name": "_owner", "type": "address"}],"name": "balanceOf","outputs": [{ "name": "balance", "type": "uint256" }],"type": "function"}]';
    contract_instance = w3.eth.contract(w3.toChecksumAddress(token), abi=get_balance_abi)
    return contract_instance.functions.balanceOf(address).call()
    
def get_total_staked(value_of_near_weth_lp, NEAR_WETH_LP_ADDRESS, NEAR_WETH_LP_DECIMALS, BRL_CHEF_ADDRESS):
    number_of_lp = get_lp_supply(NEAR_WETH_LP_ADDRESS, NEAR_WETH_LP_DECIMALS)
    lp_price = value_of_near_weth_lp / number_of_lp
    number_of_lp_staked = get_lp_staked(NEAR_WETH_LP_ADDRESS, BRL_CHEF_ADDRESS, NEAR_WETH_LP_DECIMALS)
    total_staked = number_of_lp_staked * lp_price
    return total_staked
    
def calculate_value_of_near_weth_lp(near_tokens_in_near_weth_lp, near_price, weth_tokens_in_near_weth_lp, weth_price, NEAR_WETH_LP_ADDRESS):
    value_of_near_weth_lp = near_tokens_in_near_weth_lp * near_price + weth_tokens_in_near_weth_lp * weth_price
    return value_of_near_weth_lp
    
    
def get_weekly_reward(brl_per_block, multiplier, pool_alloc_points, brl_total_alloc_points, brl_price):
    return (brl_per_block * multiplier * 604800 / 1.1 * pool_alloc_points) / brl_total_alloc_points * brl_price
    
# TODO: make token agnostic. take in the addresses as appropriate instead of hardcoded constants
# Improvement: benchmark, which calls/functions take longer and how can we speed them up? (eg call apis in parallel )
def calculate_apr(w3, brl_chef):
    start_time = time.time()
    print("calculate_apr started. Time start: " + str(start_time), file=sys.stderr) #Flask prints when it's stderr

    token_prices = get_token_prices([NEAR_ADDRESS, WETH_ADDRESS, BRL_ADDRESS])

    near_price = token_prices[NEAR_ADDRESS]["usd"]
    weth_price = token_prices[WETH_ADDRESS]["usd"]
    brl_price = token_prices[BRL_ADDRESS]["usd"]
    
    brl_per_block = brl_chef.functions.BRLPerBlock().call() / BRL_DECIMALS
    current_block_number = w3.eth.blockNumber
    multiplier = brl_chef.functions.getMultiplier(current_block_number, current_block_number + 1).call()
    pool_alloc_points = to_pool_info(brl_chef.functions.poolInfo(1).call())["allocPoint"] #TODO: sync pool index number and tokens in that pool instead of hardcoded NEAR and WETH and index 1
    brl_total_alloc_points = brl_chef.functions.totalAllocPoint().call()
    weekly_reward = get_weekly_reward(brl_per_block, multiplier, pool_alloc_points, brl_total_alloc_points, brl_price)
    
    near_tokens_in_near_weth_lp = get_gwei_balance_of_token_for_address(w3, NEAR_ADDRESS, NEAR_WETH_LP_ADDRESS)/NEAR_DECIMALS
    weth_tokens_in_near_weth_lp = get_gwei_balance_of_token_for_address(w3, WETH_ADDRESS, NEAR_WETH_LP_ADDRESS)/WETH_DECIMALS
    value_of_near_weth_lp = calculate_value_of_near_weth_lp(near_tokens_in_near_weth_lp, near_price, weth_tokens_in_near_weth_lp, weth_price, NEAR_WETH_LP_ADDRESS)
    
    total_staked = get_total_staked(value_of_near_weth_lp, NEAR_WETH_LP_ADDRESS, NEAR_WETH_LP_DECIMALS, BRL_CHEF_ADDRESS)

    apr = (weekly_reward * 52 / total_staked)
    end_time = time.time()
    print("apr: " + str(apr) + ". End time: " + str(end_time) + "; Time taken: " + str(end_time - start_time) + " seconds.", file=sys.stderr) #Flask prints when it's stderr
    return apr