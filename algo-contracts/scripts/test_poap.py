from algosdk import account, transaction
from algosdk.v2client.algod import AlgodClient
from beaker import ApplicationClient
from smart_contracts.poap import approval_program, clear_state_program  # your contract

# 1️⃣ Connect to local Algorand sandbox
algod_address = "http://localhost:4001"  # sandbox default
algod_token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
client = AlgodClient(algod_token, algod_address)

# 2️⃣ Create accounts
creator_private_key, creator_address = account.generate_account()
attendee_private_key, attendee_address = account.generate_account()
print("Creator:", creator_address)
print("Attendee:", attendee_address)

# 3️⃣ Wrap PyTeal contract in Beaker Application
from beaker.application import Application

class POAP(Application):
    approval_program = approval_program()
    clear_state_program = clear_state_program()

poap_app = POAP()

# 4️⃣ Deploy contract
app_client = ApplicationClient(client, poap_app, signer=creator_private_key)
app_id = app_client.create()
print("Application ID:", app_id)

# 5️⃣ Attendee opts in
app_client.opt_in(signer=attendee_private_key, address=attendee_address)
print("Attendee opted in")

# 6️⃣ Mint NFT
app_client.call(
    "mint",
    [
        attendee_address,    # recipient
        "1",                 # user_type
        "abcdef1234567890",  # certificate hash
        "0"                  # expires_at
    ],
    signer=creator_private_key
)
print("NFT minted for attendee!")

# 7️⃣ Verify certificate hash
app_client.call(
    "check",
    [
        attendee_address,
    ],
    signer=creator_private_key
)
result = app_client.app_state().get("last_check_result")
print("Verification result:", "✅ Valid" if result == 1 else "❌ Invalid")
