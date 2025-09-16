import os
import base64
import json
from typing import List
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from algosdk import account, mnemonic
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

# Load environment variables
load_dotenv()

DEPLOYER_MNEMONIC = os.getenv("DEPLOYER")
ALGOD_API_KEY = os.getenv("ALGOD_API_KEY")
ALGOD_API_URL = os.getenv("ALGOD_API_URL")
INDEXER_API_URL = os.getenv("INDEXER_API_URL", "https://testnet-api.4160.nodely.dev/indexer")

if not DEPLOYER_MNEMONIC:
    raise Exception("DEPLOYER mnemonic not found in environment variables")

# Init clients
if ALGOD_API_KEY and ALGOD_API_KEY.strip():
    headers = {"X-API-Key": ALGOD_API_KEY}
    algod_client = AlgodClient(ALGOD_API_KEY, ALGOD_API_URL, headers)
    indexer_client = IndexerClient(ALGOD_API_KEY, INDEXER_API_URL, headers)
else:
    algod_client = AlgodClient("", ALGOD_API_URL)
    indexer_client = IndexerClient("", INDEXER_API_URL)

# Deployer address
deployer_private_key = mnemonic.to_private_key(DEPLOYER_MNEMONIC)
deployer_address = account.address_from_private_key(deployer_private_key)


# ------------------- FastAPI Setup -------------------
app = FastAPI(
    title="Algorand POAP Verifier API",
    description="API for verifying Algorand-based Proof of Attendance NFTs.",
    version="1.0.0"
)


# ------------------- Pydantic Models -------------------
class VerifyRequest(BaseModel):
    asset_id: int


# ------------------- POAP Verifier -------------------
class POAPVerifier:
    def __init__(self, algod_client, indexer_client=None):
        self.algod_client = algod_client
        self.indexer_client = indexer_client

    def get_asset_info(self, asset_id):
        return self.algod_client.asset_info(asset_id)

    def verify_poap_structure(self, asset_info):
        params = asset_info.get("params", {})
        verification_results = {
            "is_nft": (params.get("total") == 1 and params.get("decimals") == 0),
            "correct_unit_name": params.get("unit-name") == "POAP",
            "correct_name_format": "POAP" in params.get("name", ""),
            "correct_creator": params.get("creator") == deployer_address,
        }
        return verification_results, params

    def get_asset_transactions(self, asset_id, limit=10):
        if not self.indexer_client:
            return []
        response = self.indexer_client.search_asset_transactions(asset_id=asset_id, limit=limit)
        return response.get("transactions", [])

    def extract_note_from_creation_tx(self, asset_id):
        transactions = []
        try:
            transactions = self.get_asset_transactions(asset_id, limit=50)
        except Exception as e:
            return f"[Error fetching transactions: {str(e)}]"

        for tx in transactions:
            if tx.get("tx-type") == "acfg" and tx.get("created-asset-index") == asset_id:
                note_b64 = tx.get("note")
                if not note_b64:
                    return None
                try:
                    note_bytes = base64.b64decode(note_b64, validate=False)
                    if not note_bytes:
                        return None
                    try:
                        return json.loads(note_bytes.decode("utf-8"))
                    except Exception:
                        return note_bytes.decode("utf-8", errors="ignore")
                except Exception as e:
                    return f"[Invalid note field: {str(e)}]"

        return None

    def comprehensive_verification(self, asset_id):
        asset_info = self.get_asset_info(asset_id)
        verification_results, params = self.verify_poap_structure(asset_info)

        note_content = self.extract_note_from_creation_tx(asset_id)

        passed_checks = sum(verification_results.values())
        total_checks = len(verification_results)
        overall_valid = passed_checks == total_checks

        return {
            "asset_id": asset_id,
            "asset_info": params,
            "verification_results": verification_results,
            "note_content": note_content,
            "overall_valid": overall_valid,
        }


# ------------------- API Routes -------------------
@app.post("/verify")
def verify_poap(request: VerifyRequest):
    verifier = POAPVerifier(algod_client, indexer_client)
    asset_id = request.asset_id
    # Try to fetch asset info from algod
    try:
        asset_info = verifier.algod_client.asset_info(asset_id)
    except Exception as e:
        # If asset does not exist, check via indexer (if available)
        if indexer_client:
            try:
                asset_info = indexer_client.asset_info(asset_id)
            except Exception as e2:
                # Asset truly doesn’t exist
                return {"asset_id": asset_id, "error": "asset does not exist on TestNet"}
        else:
            return {"asset_id": asset_id, "error": "asset does not exist on TestNet"}

    # If we have asset_info, continue verification
    verification_results, params = verifier.verify_poap_structure(asset_info)
    note_content = verifier.extract_note_from_creation_tx(asset_id)

    passed_checks = sum(verification_results.values())
    total_checks = len(verification_results)
    overall_valid = passed_checks == total_checks

    return {
        "asset_id": asset_id,
        "verification_results": verification_results,
        "note_content": note_content,
        "overall_valid": overall_valid
    }



@app.post("/verify-multiple")
def verify_multiple_poaps(asset_ids: List[int]):
    verifier = POAPVerifier(algod_client, indexer_client)
    results = []
    for asset_id in asset_ids:
        results.append(verifier.comprehensive_verification(asset_id))
    return results
