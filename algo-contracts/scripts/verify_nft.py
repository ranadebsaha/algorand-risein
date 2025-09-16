import os
import binascii
import json
import hashlib
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from algosdk import account, mnemonic, encoding
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Retrieve environment variables
DEPLOYER_MNEMONIC = os.getenv("DEPLOYER")
ALGOD_API_KEY = os.getenv("ALGOD_API_KEY")
ALGOD_API_URL = os.getenv("ALGOD_API_URL")
INDEXER_API_URL = os.getenv("INDEXER_API_URL", "https://testnet-api.4160.nodely.dev/indexer")

if not DEPLOYER_MNEMONIC:
    raise Exception("DEPLOYER mnemonic not found in environment variables")

# Initialize clients
if ALGOD_API_KEY and ALGOD_API_KEY.strip():
    headers = {"X-API-Key": ALGOD_API_KEY}
    algod_client = AlgodClient(ALGOD_API_KEY, ALGOD_API_URL, headers)
    indexer_client = IndexerClient(ALGOD_API_KEY, INDEXER_API_URL, headers)
else:
    algod_client = AlgodClient("", ALGOD_API_URL)
    indexer_client = IndexerClient("", INDEXER_API_URL)

# Convert mnemonic to address
deployer_private_key = mnemonic.to_private_key(DEPLOYER_MNEMONIC)
deployer_address = account.address_from_private_key(deployer_private_key)

class POAPVerifier:
    def __init__(self, algod_client, indexer_client=None):
        self.algod_client = algod_client
        self.indexer_client = indexer_client
    
    def get_asset_info(self, asset_id):
        """Get asset information from the blockchain"""
        try:
            asset_info = self.algod_client.asset_info(asset_id)
            return asset_info
        except Exception as e:
            print(f"Error retrieving asset {asset_id}: {e}")
            return None
    
    def verify_metadata_hash(self, expected_metadata, actual_metadata_hash_b64):
        """Verify if the metadata hash matches the expected certificate data"""
        try:
            # Convert certificate hash from hex to bytes (as done in minting)
            if "certificate_hash" in expected_metadata:
                cert_hash_hex = expected_metadata["certificate_hash"]
                expected_hash_bytes = binascii.unhexlify(cert_hash_hex)
                
                # Decode the actual metadata hash from base64
                actual_hash_bytes = encoding.decode_from_base64(actual_metadata_hash_b64)
                
                print(f"Expected metadata hash: {binascii.hexlify(expected_hash_bytes).decode()}")
                print(f"Actual metadata hash: {binascii.hexlify(actual_hash_bytes).decode()}")
                
                return expected_hash_bytes == actual_hash_bytes
            else:
                print("No certificate_hash found in expected metadata")
                return False
                
        except Exception as e:
            print(f"Error verifying metadata hash: {e}")
            return False
    
    def verify_poap_structure(self, asset_info, expected_metadata):
        """Verify POAP NFT structure and properties"""
        params = asset_info.get('params', {})
        
        verification_results = {
            'is_nft': False,
            'correct_unit_name': False,
            'correct_name_format': False,
            'correct_creator': False,
            'metadata_hash_valid': False,
            'has_note': False,
            'note_content_valid': False
        }
        
        # Check if it's an NFT (total=1, decimals=0)
        verification_results['is_nft'] = (
            params.get('total') == 1 and 
            params.get('decimals') == 0
        )
        
        # Check unit name
        verification_results['correct_unit_name'] = params.get('unit-name') == 'POAP'
        
        # Check asset name format (should contain "POAP")
        asset_name = params.get('name', '')
        verification_results['correct_name_format'] = 'POAP' in asset_name
        
        # Check if created by expected address (deployer)
        verification_results['correct_creator'] = params.get('creator') == deployer_address
        
        # Check metadata hash
        metadata_hash = params.get('metadata-hash')
        if metadata_hash and expected_metadata:
            verification_results['metadata_hash_valid'] = self.verify_metadata_hash(
                expected_metadata, metadata_hash
            )
        
        return verification_results, params
    
    def get_asset_transactions(self, asset_id, limit=10):
        """Get transactions related to the asset (requires indexer)"""
        if not self.indexer_client:
            print("Indexer client not available")
            return None
            
        try:
            # Get asset transactions
            response = self.indexer_client.search_asset_transactions(
                asset_id=asset_id, 
                limit=limit
            )
            return response.get('transactions', [])
        except Exception as e:
            print(f"Error getting asset transactions: {e}")
            return None
    
    def extract_note_from_creation_tx(self, asset_id):
        """Extract the note field from asset creation transaction"""
        try:
            transactions = self.get_asset_transactions(asset_id, limit=50)
            if not transactions:
                return None
            
            # Find the asset creation transaction (acfg with asset-id creation)
            for tx in transactions:
                if (tx.get('tx-type') == 'acfg' and 
                    tx.get('created-asset-index') == asset_id):
                    
                    note_b64 = tx.get('note')
                    if note_b64:
                        try:
                            note_bytes = encoding.decode_from_base64(note_b64)
                            note_text = note_bytes.decode('utf-8')
                            return json.loads(note_text)
                        except (json.JSONDecodeError, UnicodeDecodeError) as e:
                            print(f"Error decoding note: {e}")
                            return note_bytes.decode('utf-8', errors='ignore')
            
            return None
        except Exception as e:
            print(f"Error extracting note from creation tx: {e}")
            return None
    
    def verify_account_holds_asset(self, account_address, asset_id):
        """Check if an account holds the specific asset"""
        try:
            account_info = self.algod_client.account_info(account_address)
            assets = account_info.get('assets', [])
            
            for asset in assets:
                if asset.get('asset-id') == asset_id:
                    return {
                        'holds_asset': True,
                        'amount': asset.get('amount', 0),
                        'is_frozen': asset.get('is-frozen', False)
                    }
            
            return {'holds_asset': False, 'amount': 0}
        except Exception as e:
            print(f"Error checking asset holding: {e}")
            return {'holds_asset': False, 'amount': 0, 'error': str(e)}
    
    def comprehensive_verification(self, asset_id, expected_metadata=None, holder_address=None):
        """Perform comprehensive POAP verification"""
        print(f"\n{'='*50}")
        print(f"COMPREHENSIVE POAP VERIFICATION")
        print(f"Asset ID: {asset_id}")
        print(f"{'='*50}")
        
        # Get asset information
        asset_info = self.get_asset_info(asset_id)
        if not asset_info:
            return {"error": "Asset not found"}
        
        # Basic asset verification
        verification_results, params = self.verify_poap_structure(asset_info, expected_metadata)
        
        print(f"\n📋 ASSET PROPERTIES:")
        print(f"   Name: {params.get('name')}")
        print(f"   Unit Name: {params.get('unit-name')}")
        print(f"   Total Supply: {params.get('total')}")
        print(f"   Decimals: {params.get('decimals')}")
        print(f"   Creator: {params.get('creator')}")
        print(f"   URL: {params.get('url')}")
        
        print(f"\n✅ VERIFICATION RESULTS:")
        for check, result in verification_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {check.replace('_', ' ').title()}: {status}")
        
        # Extract and verify note content
        print(f"\n📝 NOTE CONTENT VERIFICATION:")
        note_content = self.extract_note_from_creation_tx(asset_id)
        if note_content:
            print(f"   Found note in creation transaction:")
            if isinstance(note_content, dict):
                for key, value in note_content.items():
                    print(f"     {key}: {value}")
                
                # Compare with expected metadata
                if expected_metadata:
                    note_matches = self.compare_metadata(note_content, expected_metadata)
                    status = "✅ PASS" if note_matches else "❌ FAIL"
                    print(f"   Note matches expected metadata: {status}")
            else:
                print(f"     Raw note: {note_content}")
        else:
            print(f"   No note found in creation transaction")
        
        # Check asset holding (if holder address provided)
        if holder_address:
            print(f"\n👤 HOLDER VERIFICATION:")
            print(f"   Checking address: {holder_address}")
            holding_info = self.verify_account_holds_asset(holder_address, asset_id)
            
            if holding_info['holds_asset']:
                print(f"   ✅ Account holds the asset")
                print(f"   Amount: {holding_info['amount']}")
                if 'is_frozen' in holding_info:
                    frozen_status = "❄️ FROZEN" if holding_info['is_frozen'] else "🔓 UNFROZEN"
                    print(f"   Status: {frozen_status}")
            else:
                print(f"   ❌ Account does not hold the asset")
                if 'error' in holding_info:
                    print(f"   Error: {holding_info['error']}")
        
        # Overall assessment
        passed_checks = sum(verification_results.values())
        total_checks = len(verification_results)
        
        print(f"\n🎯 OVERALL ASSESSMENT:")
        print(f"   Passed: {passed_checks}/{total_checks} checks")
        
        if passed_checks == total_checks:
            print(f"   🏆 VALID POAP NFT")
        elif passed_checks >= total_checks * 0.7:
            print(f"   ⚠️  MOSTLY VALID (some issues detected)")
        else:
            print(f"   ❌ INVALID POAP NFT")
        
        return {
            'asset_id': asset_id,
            'asset_info': params,
            'verification_results': verification_results,
            'note_content': note_content,
            'holder_info': self.verify_account_holds_asset(holder_address, asset_id) if holder_address else None,
            'overall_valid': passed_checks == total_checks
        }
    
    def compare_metadata(self, note_metadata, expected_metadata):
        """Compare note metadata with expected metadata"""
        if not isinstance(note_metadata, dict) or not isinstance(expected_metadata, dict):
            return False
        
        for key, expected_value in expected_metadata.items():
            if key not in note_metadata:
                return False
            if note_metadata[key] != expected_value:
                return False
        
        return True

def verify_poap_by_asset_id(asset_id, expected_metadata=None, holder_address=None):
    """Main verification function"""
    verifier = POAPVerifier(algod_client, indexer_client)
    return verifier.comprehensive_verification(asset_id, expected_metadata, holder_address)

def verify_multiple_poaps(asset_ids, expected_metadata_list=None):
    """Verify multiple POAP assets"""
    verifier = POAPVerifier(algod_client, indexer_client)
    
    results = []
    for i, asset_id in enumerate(asset_ids):
        expected = expected_metadata_list[i] if expected_metadata_list and i < len(expected_metadata_list) else None
        result = verifier.comprehensive_verification(asset_id, expected)
        results.append(result)
    
    return results

if __name__ == "__main__":
    # Example usage - replace with your actual asset ID
    test_asset_id = 745898097  # Replace with actual POAP asset ID
    
    # Expected metadata that should match what was used during minting
    expected_poap_metadata = {
        "event": "Rise Hackathon 2025",
        "organizer": "University Institute of Technology", 
        "date": "2025-09-16",
        "certificate_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    }
    
    # Optional: Check if specific address holds the POAP
    holder_to_check = "YOUR_ADDRESS_HERE"  # Replace with actual address
    
    # Perform verification
    print("🔍 Starting POAP Verification...")
    
    try:
        result = verify_poap_by_asset_id(
            asset_id=test_asset_id,
            expected_metadata=expected_poap_metadata,
            holder_address=holder_to_check
        )
        
        if result.get('overall_valid'):
            print(f"\n🎉 SUCCESS: Asset {test_asset_id} is a valid POAP!")
        else:
            print(f"\n⚠️  WARNING: Asset {test_asset_id} has verification issues.")
            
    except Exception as e:
        print(f"\n❌ ERROR during verification: {e}")
    
    # Example: Verify multiple POAPs
    # multiple_assets = [123456789, 123456790, 123456791]
    # results = verify_multiple_poaps(multiple_assets)
