import os
import binascii
import json
from algosdk.v2client.algod import AlgodClient
from algosdk import account, mnemonic
from algosdk.transaction import AssetConfigTxn, wait_for_confirmation
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Retrieve environment variables
DEPLOYER_MNEMONIC = os.getenv("DEPLOYER")
ALGOD_API_KEY = os.getenv("ALGOD_API_KEY")
ALGOD_API_URL = os.getenv("ALGOD_API_URL")

if not DEPLOYER_MNEMONIC:
    raise Exception("DEPLOYER mnemonic not found in environment variables")

# Initialize Algod client correctly
if ALGOD_API_KEY and ALGOD_API_KEY.strip():
    headers = {"X-API-Key": ALGOD_API_KEY}
    algod_client = AlgodClient(ALGOD_API_KEY, ALGOD_API_URL, headers)
else:
    algod_client = AlgodClient("", ALGOD_API_URL)

# Convert mnemonic to private key and derive public address
deployer_private_key = mnemonic.to_private_key(DEPLOYER_MNEMONIC)
deployer_address = account.address_from_private_key(deployer_private_key)

def mint_nft(nft_metadata):
    # Convert certificate hash from hex string to bytes
    cert_hash_hex = nft_metadata["certificate_hash"]
    metadata_hash_bytes = binascii.unhexlify(cert_hash_hex)

    # Encode the full JSON metadata as bytes for 'note' field
    note = json.dumps(nft_metadata).encode()

    # Fetch suggested transaction parameters
    try:
        params = algod_client.suggested_params()
    except Exception as e:
        print("Error fetching suggested params:", e)
        return None

    txn = AssetConfigTxn(
    sender=deployer_address,
    sp=params,
    total=1,
    default_frozen=False,
    unit_name="POAP",
    asset_name="POAP-RiseHack25-RDS",
    manager="",
    reserve="",
    freeze="",
    clawback="",
    url="https://yourapp.example/metadata.json",
    metadata_hash=metadata_hash_bytes,
    note=note,
    decimals=0,
    strict_empty_address_check=False
)

    
    signed_txn = txn.sign(deployer_private_key)

    try:
        
        txid = algod_client.send_transaction(signed_txn)
        print(f"Transaction sent with txID: {txid}")

       
        wait_for_confirmation(algod_client, txid, 4)

      
        ptx = algod_client.pending_transaction_info(txid)
        asset_id = ptx['asset-index']

        print(f"NFT minted! Asset ID: {asset_id}")
        return asset_id
    except Exception as e:
        print("Error sending transaction:", e)
        return None


if __name__ == "__main__":
    
    nft_metadata_example = {
        "event": "Rise Hackathon 2025",
        "organizer": "University Institute of Technology",
        "date": "2025-09-16",
        "certificate_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    }
    mint_nft(nft_metadata_example)
