import os
import binascii
import json
import base64
import hashlib
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from algosdk.error import AlgodHTTPError

# Load environment variables
load_dotenv()

# Network selection: 'testnet' or 'mainnet'
NETWORK = os.getenv("NETWORK", "testnet").lower()

if NETWORK == "mainnet":
    ALGOD_API_URL = os.getenv("ALGOD_API_URL", "https://mainnet-api.algonode.cloud")
    INDEXER_API_URL = os.getenv("INDEXER_API_URL", "https://mainnet-idx.algonode.cloud")
else:
    ALGOD_API_URL = os.getenv("ALGOD_API_URL", "https://testnet-api.algonode.cloud")
    INDEXER_API_URL = os.getenv("INDEXER_API_URL", "https://testnet-idx.algonode.cloud")

ALGOD_API_KEY = os.getenv("ALGOD_API_KEY", "")

# Initialize clients
headers = {"X-API-Key": ALGOD_API_KEY} if ALGOD_API_KEY else {}
algod_client = AlgodClient(ALGOD_API_KEY, ALGOD_API_URL, headers)
indexer_client = IndexerClient(ALGOD_API_KEY, INDEXER_API_URL, headers)

app = FastAPI(title="POAP Certificate Extractor API")

# Request model
class AssetRequest(BaseModel):
    asset_id: int

# Helper functions
def get_certificate_details_from_asset_id(asset_id):
    try:
        asset_info = algod_client.asset_info(asset_id)
        params = asset_info.get("params", {})

        # Extract certificate hash
        metadata_hash_b64 = params.get("metadata-hash", "")
        certificate_hash = None
        if metadata_hash_b64:
            try:
                certificate_hash = binascii.hexlify(base64.b64decode(metadata_hash_b64)).decode()
            except:
                certificate_hash = None

        # Fetch creation transaction
        full_metadata = {}
        try:
            response = indexer_client.search_asset_transactions(
                asset_id=asset_id, tx_type="acfg", limit=50
            )
            transactions = response.get("transactions", [])
            creation_tx = next(
                (tx for tx in transactions if tx.get("tx-type") == "acfg" and tx.get("created-asset-index") == asset_id),
                None
            )

            if creation_tx:
                note_b64 = creation_tx.get("note", "")
                if note_b64:
                    note_bytes = base64.b64decode(note_b64)
                    full_metadata = json.loads(note_bytes.decode("utf-8"))
        except:
            pass

        # Certificate details
        certificate_details = {
            "event": full_metadata.get("event", "Data not available"),
            "organizer": full_metadata.get("organizer", "Data not available"),
            "date": full_metadata.get("date", "Data not available"),
            "recipient_name": full_metadata.get("recipient_name", "Data not available"),
            "recipient_address": full_metadata.get("recipient_address", "Data not available"),
            "issued_at": full_metadata.get("issued_at"),
            "poap_version": full_metadata.get("poap_version"),
            "type": full_metadata.get("type")
        }

        asset_basic_info = {
            "name": params.get("name"),
            "creator": params.get("creator"),
            "url": params.get("url"),
            "unit_name": params.get("unit-name")
        }

        return {
            "success": True,
            "asset_id": asset_id,
            "certificate_hash": certificate_hash,
            "certificate_details": certificate_details,
            "asset_info": asset_basic_info,
            "full_metadata": full_metadata
        }

    except AlgodHTTPError as e:
        # Asset does not exist or other Algod errors
        return {
            "success": False,
            "asset_id": asset_id,
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "asset_id": asset_id,
            "error": f"Unexpected error: {e}"
        }

# Endpoint
@app.post("/get-certificate/")
async def get_certificate(request: AssetRequest):
    result = get_certificate_details_from_asset_id(request.asset_id)
    return result

@app.get("/")
async def root():
    return {
        "message": "POAP Certificate Extractor API. Use POST /get-certificate/ with JSON {\"asset_id\": <id>}."
    }
