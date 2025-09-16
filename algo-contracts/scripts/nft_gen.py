import os
import binascii
import json
from algosdk.v2client.algod import AlgodClient
from algosdk import account, mnemonic
from algosdk.transaction import AssetConfigTxn, AssetTransferTxn, wait_for_confirmation, assign_group_id
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

def check_account_exists(address):
    """Check if account exists and has sufficient balance"""
    try:
        account_info = algod_client.account_info(address)
        balance = account_info['amount']
        print(f"✅ Account {address[:8]}... exists with balance: {balance / 1000000:.6f} ALGO")
        return True, balance
    except Exception as e:
        print(f"❌ Error checking account {address[:8]}...: {e}")
        return False, 0

def check_asset_opt_in(user_address, asset_id):
    """Check if user has opted in to an asset"""
    try:
        account_info = algod_client.account_info(user_address)
        assets = account_info.get('assets', [])
        
        for asset in assets:
            if asset.get('asset-id') == asset_id:
                return True
        return False
    except Exception as e:
        print(f"Error checking opt-in status: {e}")
        return False

def mint_and_transfer_poap(nft_metadata, user_address, auto_optin=True):
    """
    Mint POAP NFT and transfer to user wallet
    
    Args:
        nft_metadata: Dictionary containing event metadata
        user_address: Recipient's wallet address
        auto_optin: Whether to automatically handle opt-in (requires user cooperation)
    
    Returns:
        Dictionary with asset_id, transaction_ids, and status
    """
    
    print(f"\n🎫 Starting POAP Minting and Transfer Process")
    print(f"📅 Event: {nft_metadata.get('event', 'Unknown Event')}")
    print(f"👤 Recipient: {user_address[:8]}...{user_address[-8:]}")
    print(f"{'='*60}")
    
    # Validate user address and check account
    try:
        # Check if user account exists
        user_exists, user_balance = check_account_exists(user_address)
        if not user_exists:
            return {
                'success': False,
                'error': 'User account does not exist or is not funded',
                'asset_id': None
            }
        
        # Check minimum balance for asset opt-in (0.1 ALGO = 100,000 microALGO)
        if user_balance < 100000:
            print(f"⚠️  Warning: User balance ({user_balance / 1000000:.6f} ALGO) may be insufficient for asset opt-in")
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Error validating user account: {e}',
            'asset_id': None
        }
    
    # Step 1: Create the POAP NFT
    print(f"\n🏭 Step 1: Creating POAP NFT...")
    
    try:
        # Convert certificate hash from hex string to bytes
        cert_hash_hex = nft_metadata["certificate_hash"]
        metadata_hash_bytes = binascii.unhexlify(cert_hash_hex)

        # Encode the full JSON metadata as bytes for 'note' field
        note = json.dumps(nft_metadata).encode()

        # Fetch suggested transaction parameters
        params = algod_client.suggested_params()

        # Create asset configuration transaction
        asset_creation_txn = AssetConfigTxn(
            sender=deployer_address,
            sp=params,
            total=1,
            default_frozen=False,
            unit_name="POAP",
            asset_name=f"POAP-{nft_metadata.get('event', 'Event')[:15]}",
            manager=deployer_address,  # Keep manager to enable transfers
            reserve=deployer_address,
            freeze=deployer_address,
            clawback=deployer_address,
            url=nft_metadata.get('url', "https://yourapp.example/metadata.json"),
            metadata_hash=metadata_hash_bytes,
            note=note,
            decimals=0,
            strict_empty_address_check=False
        )

        # Sign and send asset creation transaction
        signed_asset_txn = asset_creation_txn.sign(deployer_private_key)
        asset_txid = algod_client.send_transaction(signed_asset_txn)
        
        print(f"📝 Asset creation transaction sent: {asset_txid}")
        
        # Wait for confirmation
        wait_for_confirmation(algod_client, asset_txid, 4)
        
        # Get the created asset ID
        ptx = algod_client.pending_transaction_info(asset_txid)
        asset_id = ptx['asset-index']
        
        print(f"✅ NFT created successfully! Asset ID: {asset_id}")
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Error creating asset: {e}',
            'asset_id': None
        }
    
    # Step 2: Check if user needs to opt-in to the asset
    print(f"\n🔍 Step 2: Checking user opt-in status...")
    
    user_opted_in = check_asset_opt_in(user_address, asset_id)
    
    if not user_opted_in:
        print(f"❌ User has not opted in to asset {asset_id}")
        
        if auto_optin:
            print(f"ℹ️  Note: User must opt-in to receive the asset.")
            print(f"ℹ️  The user can opt-in by sending a 0-amount asset transfer to themselves.")
            print(f"ℹ️  Asset ID to opt-in: {asset_id}")
            
            return {
                'success': False,
                'error': 'User must opt-in to the asset before receiving it',
                'asset_id': asset_id,
                'asset_creation_txid': asset_txid,
                'opt_in_required': True,
                'instructions': f"User must opt-in to asset {asset_id} before receiving the POAP"
            }
        else:
            print(f"⏭️  Proceeding without opt-in check (transfer will fail if user hasn't opted in)")
    else:
        print(f"✅ User has already opted in to asset {asset_id}")
    
    # Step 3: Transfer the POAP to user
    print(f"\n📤 Step 3: Transferring POAP to user...")
    
    try:
        # Get fresh transaction parameters for transfer
        params = algod_client.suggested_params()
        
        # Create asset transfer transaction
        transfer_txn = AssetTransferTxn(
            sender=deployer_address,
            sp=params,
            receiver=user_address,
            amt=1,
            index=asset_id
        )
        
        # Sign and send transfer transaction
        signed_transfer_txn = transfer_txn.sign(deployer_private_key)
        transfer_txid = algod_client.send_transaction(signed_transfer_txn)
        
        print(f"📝 Transfer transaction sent: {transfer_txid}")
        
        # Wait for confirmation
        wait_for_confirmation(algod_client, transfer_txid, 4)
        
        print(f"✅ POAP transferred successfully to user!")
        
        return {
            'success': True,
            'asset_id': asset_id,
            'asset_creation_txid': asset_txid,
            'transfer_txid': transfer_txid,
            'recipient': user_address,
            'event': nft_metadata.get('event'),
            'message': f'POAP successfully minted and transferred to {user_address[:8]}...{user_address[-8:]}'
        }
        
    except Exception as e:
        print(f"❌ Error transferring asset: {e}")
        
        # Asset was created but transfer failed
        return {
            'success': False,
            'error': f'Asset created but transfer failed: {e}',
            'asset_id': asset_id,
            'asset_creation_txid': asset_txid,
            'transfer_failed': True,
            'possible_cause': 'User may not have opted in to the asset'
        }

def batch_mint_and_transfer(nft_metadata, user_addresses):
    """
    Mint and transfer POAPs to multiple users
    
    Args:
        nft_metadata: Base metadata (event info)
        user_addresses: List of recipient addresses
    
    Returns:
        List of results for each recipient
    """
    
    print(f"\n🎫 Starting Batch POAP Distribution")
    print(f"📅 Event: {nft_metadata.get('event')}")
    print(f"👥 Recipients: {len(user_addresses)} users")
    print(f"{'='*60}")
    
    results = []
    
    for i, user_address in enumerate(user_addresses, 1):
        print(f"\n--- Processing recipient {i}/{len(user_addresses)} ---")
        
        # Create unique metadata for each recipient
        unique_metadata = nft_metadata.copy()
        unique_metadata['recipient_number'] = i
        unique_metadata['certificate_hash'] = f"{nft_metadata['certificate_hash']}{i:02d}"  # Make unique
        
        result = mint_and_transfer_poap(unique_metadata, user_address, auto_optin=True)
        results.append(result)
        
        if result['success']:
            print(f"✅ Recipient {i} completed successfully")
        else:
            print(f"❌ Recipient {i} failed: {result.get('error', 'Unknown error')}")
    
    # Summary
    successful = sum(1 for r in results if r['success'])
    print(f"\n📊 Batch Distribution Summary:")
    print(f"   ✅ Successful: {successful}/{len(user_addresses)}")
    print(f"   ❌ Failed: {len(user_addresses) - successful}/{len(user_addresses)}")
    
    return results

def create_opt_in_instructions(asset_id):
    """Generate instructions for user to opt-in to the asset"""
    
    instructions = f"""
    🔧 ASSET OPT-IN INSTRUCTIONS
    
    Asset ID: {asset_id}
    
    The user must opt-in to receive this POAP. Here are the options:
    
    Option 1 - Using Pera Wallet (Recommended):
    1. Open Pera Wallet mobile app
    2. Go to "Collectibles" or "Assets" section
    3. Tap "+" to add new asset
    4. Enter Asset ID: {asset_id}
    5. Confirm opt-in transaction
    
    Option 2 - Using AlgoDesk:
    1. Go to https://app.algodesk.io
    2. Connect your wallet
    3. Click "Add Asset"
    4. Enter Asset ID: {asset_id}
    5. Complete opt-in transaction
    
    Option 3 - Programmatically (for developers):
    Send a 0-amount asset transfer transaction from user to themselves.
    
    After opt-in is complete, the POAP can be transferred to the user.
    """
    
    return instructions

if __name__ == "__main__":
    # Example usage
    nft_metadata_example = {
        "event": "Rise Hackathon 2025",
        "organizer": "University Institute of Technology",
        "date": "2025-09-16", 
        "certificate_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "url": "https://yourapp.example/metadata.json"
    }
    
    # Single user example
    user_wallet_address = "73H6VSES3MVAFPRS5IFQFDHMVIEBVEN7PEZ2A7USKWO7VTV5QT7S7GNYCU"  # Replace with actual address
    
    # Uncomment to test single user
    result = mint_and_transfer_poap(nft_metadata_example, user_wallet_address)
    print(f"\n🎯 Final Result: {result}")
    
    if not result['success'] and result.get('opt_in_required'):
        print(create_opt_in_instructions(result['asset_id']))
    
    # Multiple users example
    # user_addresses = [
    #     "USER_ADDRESS_1",
    #     "USER_ADDRESS_2", 
    #     "USER_ADDRESS_3"
    # ]
    
    # Uncomment to test batch distribution
    # batch_results = batch_mint_and_transfer(nft_metadata_example, user_addresses)
    
    print(f"\n⚠️  Please replace placeholder addresses with actual Algorand addresses to test!")
    print(f"📝 Make sure recipient addresses have:")
    print(f"   • Sufficient ALGO balance (≥ 0.1 ALGO for opt-in)")  
    print(f"   • Opted in to the POAP asset (or use auto opt-in flow)")
