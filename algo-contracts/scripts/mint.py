import os
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from algosdk.v2client.algod import AlgodClient
from algosdk import account, mnemonic
from algosdk.transaction import AssetConfigTxn, wait_for_confirmation
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# --- Gmail SMTP Config ---
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")

# --- Algorand Config ---
DEPLOYER_MNEMONIC = os.getenv("DEPLOYER")
ALGOD_API_KEY = os.getenv("ALGOD_API_KEY")
ALGOD_API_URL = os.getenv("ALGOD_API_URL")

if not all([DEPLOYER_MNEMONIC, ALGOD_API_URL]):
    raise Exception("Missing required environment variables: DEPLOYER or ALGOD_API_URL")

# Initialize Algod client
headers = {"X-API-Key": ALGOD_API_KEY} if ALGOD_API_KEY and ALGOD_API_KEY.strip() else {}
algod_client = AlgodClient(ALGOD_API_KEY, ALGOD_API_URL, headers)

# Deployer account
deployer_private_key = mnemonic.to_private_key(DEPLOYER_MNEMONIC)
deployer_address = account.address_from_private_key(deployer_private_key)

# --- FastAPI Setup ---
app = FastAPI(title="Algorand NFT Minting API", version="1.0.0")

# --- Pydantic Model ---
class NFTPayload(BaseModel):
    event: str
    organizer: str
    date: str
    certificate_hash: str
    email: str   # user email to receive minted asset info


def send_email(to_email: str, txid: str, asset_id: int):
    """Send Gmail notification to user with minted asset details."""
    if not GMAIL_USER or not GMAIL_PASS:
        print("⚠️ Gmail credentials missing. Skipping email.")
        return False

    subject = "Your NFT has been minted!"
    body = f"""
    Congratulations 🎉

    Your NFT has been successfully minted on Algorand.

    ▸ Transaction ID: {txid}
    ▸ Asset ID: {asset_id}

    You can look it up on AlgoExplorer:
    https://testnet.explorer.perawallet.app/asset/{asset_id}

    Regards,
    Algorand NFT Service
    """

    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASS)
        server.send_message(msg)
        server.quit()

        print(f"📧 Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False


# --- API Endpoint ---
@app.post("/mint", tags=["NFT Minting"])
async def mint_nft(nft_payload: NFTPayload):
    try:
        # Hash certificate string → 32-byte digest
        digest = hashlib.sha256(nft_payload.certificate_hash.encode()).digest()

        # JSON metadata as note
        note = nft_payload.json().encode()

        # Txn params
        params = algod_client.suggested_params()

        # Create NFT (ASA)
        txn = AssetConfigTxn(
            sender=deployer_address,
            sp=params,
            total=1,
            default_frozen=False,
            unit_name="POAP",
            asset_name=f"POAP-{nft_payload.event}",
            manager="",
            reserve="",
            freeze="",
            clawback="",
            url="https://yourapp.example/metadata.json",
            metadata_hash=digest,
            note=note,
            decimals=0,
            strict_empty_address_check=False
        )

        # Sign & send
        signed_txn = txn.sign(deployer_private_key)
        txid = algod_client.send_transaction(signed_txn)
        print(f"✅ Transaction sent: {txid}")

        wait_for_confirmation(algod_client, txid, 4)

        # Get Asset ID
        ptx = algod_client.pending_transaction_info(txid)
        asset_id = ptx.get("asset-index")
        if not asset_id:
            raise HTTPException(status_code=500, detail="Failed to retrieve asset ID")

        print(f"🎉 NFT minted: Asset ID {asset_id}")

        # Send Gmail
        email_status = send_email(nft_payload.email, txid, asset_id)

        return {
            "txID": txid,
            "assetID": asset_id,
            "email_sent": email_status
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
