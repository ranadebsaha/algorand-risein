import os
import binascii
import json
import base64
import hashlib
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ALGOD_API_KEY = os.getenv("ALGOD_API_KEY")
ALGOD_API_URL = os.getenv("ALGOD_API_URL")
INDEXER_API_URL = os.getenv("INDEXER_API_URL", "https://testnet-api.4160.nodely.dev/indexer")

# Initialize clients
if ALGOD_API_KEY and ALGOD_API_KEY.strip():
    headers = {"X-API-Key": ALGOD_API_KEY}
    algod_client = AlgodClient(ALGOD_API_KEY, ALGOD_API_URL, headers)
    indexer_client = IndexerClient(ALGOD_API_KEY, INDEXER_API_URL, headers)
else:
    algod_client = AlgodClient("", ALGOD_API_URL)
    indexer_client = IndexerClient("", INDEXER_API_URL)

def get_certificate_details_from_asset_id(asset_id):
    """
    Extract certificate details and hash from NFT Asset ID
    Returns the original data that was used to create the NFT
    """
    
    print(f"\n🔍 Extracting Certificate Details from Asset ID: {asset_id}")
    print("=" * 60)
    
    try:
        # Step 1: Get asset basic info
        print("📊 Getting asset information...")
        asset_info = algod_client.asset_info(asset_id)
        params = asset_info.get('params', {})
        
        print(f"✅ Asset found: {params.get('name', 'Unknown')}")
        
        # Step 2: Extract certificate hash from metadata_hash field
        metadata_hash_b64 = params.get('metadata-hash', '')
        certificate_hash = None
        
        if metadata_hash_b64:
            try:
                # Decode the metadata hash back to hex string
                metadata_hash_bytes = base64.b64decode(metadata_hash_b64)
                certificate_hash = binascii.hexlify(metadata_hash_bytes).decode()
                print(f"🔐 Certificate Hash: {certificate_hash}")
            except Exception as e:
                print(f"⚠️  Could not decode certificate hash: {e}")
        
        # Step 3: Get creation transaction to extract full metadata from note
        print("\n🔍 Searching for creation transaction...")
        
        try:
            response = indexer_client.search_asset_transactions(
                asset_id=asset_id,
                tx_type='acfg',
                limit=50
            )
            
            transactions = response.get('transactions', [])
            creation_tx = None
            
            # Find the asset creation transaction
            for tx in transactions:
                if (tx.get('tx-type') == 'acfg' and 
                    tx.get('created-asset-index') == asset_id):
                    creation_tx = tx
                    break
            
            if creation_tx:
                print(f"✅ Found creation transaction: {creation_tx.get('id', 'Unknown')[:16]}...")
                
                # Extract metadata from note field
                note_b64 = creation_tx.get('note', '')
                if note_b64:
                    try:
                        # Decode the note field
                        note_bytes = base64.b64decode(note_b64)
                        note_text = note_bytes.decode('utf-8')
                        
                        # Parse JSON metadata
                        full_metadata = json.loads(note_text)
                        
                        print(f"✅ Successfully extracted metadata from transaction note!")
                        
                        return {
                            'success': True,
                            'asset_id': asset_id,
                            'certificate_hash': certificate_hash,
                            'certificate_details': {
                                'event': full_metadata.get('event'),
                                'organizer': full_metadata.get('organizer'),
                                'date': full_metadata.get('date'),
                                'recipient_name': full_metadata.get('recipient_name'),
                                'recipient_address': full_metadata.get('recipient_address'),
                                'issued_at': full_metadata.get('issued_at'),
                                'poap_version': full_metadata.get('poap_version'),
                                'type': full_metadata.get('type')
                            },
                            'asset_info': {
                                'name': params.get('name'),
                                'creator': params.get('creator'),
                                'url': params.get('url'),
                                'unit_name': params.get('unit-name')
                            },
                            'full_metadata': full_metadata
                        }
                        
                    except Exception as e:
                        print(f"❌ Could not parse transaction note: {e}")
                else:
                    print(f"⚠️  No note field found in creation transaction")
            else:
                print(f"⚠️  Creation transaction not found")
        
        except Exception as e:
            print(f"⚠️  Indexer search failed: {e}")
        
        # Fallback: Return basic info if full metadata not available
        return {
            'success': True,
            'asset_id': asset_id,
            'certificate_hash': certificate_hash,
            'certificate_details': {
                'event': 'Data not available in transaction note',
                'organizer': 'Data not available',
                'date': 'Data not available',
                'recipient_name': 'Data not available',
                'recipient_address': 'Data not available'
            },
            'asset_info': {
                'name': params.get('name'),
                'creator': params.get('creator'),
                'url': params.get('url'),
                'unit_name': params.get('unit-name')
            },
            'note': 'Full metadata not available - only certificate hash extracted'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to retrieve asset information: {e}',
            'asset_id': asset_id
        }

def verify_certificate_hash(certificate_details, certificate_hash):
    """
    Verify if the certificate details match the hash
    """
    if not certificate_hash or not certificate_details:
        return False
    
    # Recreate the hash from certificate details
    hash_input = f"{certificate_details['event']}|{certificate_details['organizer']}|{certificate_details['date']}|{certificate_details['recipient_name']}|{certificate_details['recipient_address']}"
    calculated_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
    
    return calculated_hash == certificate_hash

def display_certificate_info(result):
    """
    Display certificate information in a clean format
    """
    
    print(f"\n📋 CERTIFICATE DETAILS")
    print("=" * 40)
    
    if result['success']:
        details = result['certificate_details']
        
        print(f"🎫 Asset ID: {result['asset_id']}")
        print(f"🔐 Certificate Hash: {result.get('certificate_hash', 'Not available')}")
        print()
        print(f"📅 Event: {details['event']}")
        print(f"🏢 Organizer: {details['organizer']}")
        print(f"📆 Date: {details['date']}")
        print(f"👤 Recipient: {details['recipient_name']}")
        print(f"💳 Wallet: {details['recipient_address']}")
        
        if details.get('issued_at'):
            print(f"⏰ Issued At: {details['issued_at']}")
        
        # Verify hash if available
        if result.get('certificate_hash') and details['event'] != 'Data not available in transaction note':
            is_valid = verify_certificate_hash(details, result['certificate_hash'])
            print(f"✅ Hash Verification: {'VALID ✓' if is_valid else 'INVALID ✗'}")
        
        print(f"\n🔗 Asset Info:")
        asset_info = result['asset_info']
        print(f"   Name: {asset_info['name']}")
        print(f"   Creator: {asset_info['creator']}")
        print(f"   URL: {asset_info['url']}")
        
    else:
        print(f"❌ Error: {result['error']}")

# Usage Example
if __name__ == "__main__":
    print("🎫 POAP Certificate Details Extractor")
    print("Input: Asset ID → Output: Certificate Details + Hash")
    
    # Replace with your actual Asset ID
    asset_id = 745899830  
    
    # Extract certificate details
    result = get_certificate_details_from_asset_id(asset_id)
    
    # Display the results
    display_certificate_info(result)
    
    # If you want just the raw data
    if result['success']:
        print(f"\n📊 RAW DATA (JSON):")
        print("-" * 30)
        print(json.dumps(result, indent=2))
        
        # Just the certificate hash
        print(f"\n🔐 CERTIFICATE HASH ONLY:")
        print(result.get('certificate_hash', 'Not available'))
        
        # Just the certificate details
        print(f"\n📋 CERTIFICATE DETAILS ONLY:")
        for key, value in result['certificate_details'].items():
            print(f"{key}: {value}")
