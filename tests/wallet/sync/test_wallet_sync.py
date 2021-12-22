# flake8: noqa: F811, F401
import asyncio

import pytest
from typing import List
from colorlog import getLogger

from chia.consensus.block_rewards import calculate_base_farmer_reward, calculate_pool_reward
from chia.protocols import full_node_protocol
from chia.protocols.shared_protocol import Capability
from chia.simulator.simulator_protocol import FarmNewBlockProtocol
from chia.types.full_block import FullBlock
from chia.types.peer_info import PeerInfo
from chia.util.ints import uint16, uint32
from chia.wallet.wallet_state_manager import WalletStateManager
from tests.connection_utils import disconnect_all_and_reconnect
from tests.setup_nodes import bt, self_hostname, setup_node_and_wallet, setup_simulators_and_wallets, test_constants
from tests.time_out_assert import time_out_assert


def wallet_height_at_least(wallet_node, h):
    height = wallet_node.wallet_state_manager.blockchain._peak_height
    if height == h:
        return True
    return False


log = getLogger(__name__)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop


class TestWalletSync:
    @pytest.fixture(scope="function")
    async def wallet_node(self):
        async for _ in setup_node_and_wallet(test_constants):
            yield _

    @pytest.fixture(scope="function")
    async def wallet_node_simulator(self):
        async for _ in setup_simulators_and_wallets(1, 1, {}):
            yield _

    @pytest.fixture(scope="function")
    async def two_nodes_two_wallets(self):
        async for _ in setup_simulators_and_wallets(2, 2, {}):
            yield _

    @pytest.fixture(scope="function")
    async def wallet_node_starting_height(self):
        async for _ in setup_node_and_wallet(test_constants, starting_height=100):
            yield _

    @pytest.mark.asyncio
    async def test_basic_sync_wallet(self, wallet_node, default_400_blocks):

        full_node_api, wallet_node, full_node_server, wallet_server = wallet_node

        for block in default_400_blocks:
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(block))

        await wallet_server.start_client(PeerInfo(self_hostname, uint16(full_node_server._port)), None)

        # The second node should eventually catch up to the first one, and have the
        # same tip at height num_blocks - 1.
        await time_out_assert(100, wallet_height_at_least, True, wallet_node, len(default_400_blocks) - 1)

        # Tests a reorg with the wallet
        num_blocks = 30
        blocks_reorg = bt.get_consecutive_blocks(num_blocks, block_list_input=default_400_blocks[:-5])
        for i in range(1, len(blocks_reorg)):
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(blocks_reorg[i]))

        await disconnect_all_and_reconnect(wallet_server, full_node_server)

        await time_out_assert(
            100, wallet_height_at_least, True, wallet_node, len(default_400_blocks) + num_blocks - 5 - 1
        )

    @pytest.mark.asyncio
    async def test_backtrack_sync_wallet(self, wallet_node, default_400_blocks):

        full_node_api, wallet_node, full_node_server, wallet_server = wallet_node
        for block in default_400_blocks[:20]:
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(block))

        await wallet_server.start_client(PeerInfo(self_hostname, uint16(full_node_server._port)), None)

        # The second node should eventually catch up to the first one, and have the
        # same tip at height num_blocks - 1.
        await time_out_assert(100, wallet_height_at_least, True, wallet_node, 19)
        # Tests a reorg with the wallet

    @pytest.mark.asyncio
    async def test_short_batch_sync_wallet(self, wallet_node, default_400_blocks):

        full_node_api, wallet_node, full_node_server, wallet_server = wallet_node

        for block in default_400_blocks[:200]:
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(block))

        await wallet_server.start_client(PeerInfo(self_hostname, uint16(full_node_server._port)), None)

        # The second node should eventually catch up to the first one, and have the
        # same tip at height num_blocks - 1.
        await time_out_assert(100, wallet_height_at_least, True, wallet_node, 199)
        # Tests a reorg with the wallet

    @pytest.mark.asyncio
    async def test_long_sync_wallet(self, wallet_node, default_1000_blocks, default_400_blocks):

        full_node_api, wallet_node, full_node_server, wallet_server = wallet_node

        for block in default_400_blocks:
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(block))

        await wallet_server.start_client(PeerInfo(self_hostname, uint16(full_node_server._port)), None)

        # The second node should eventually catch up to the first one, and have the
        # same tip at height num_blocks - 1.
        await time_out_assert(600, wallet_height_at_least, True, wallet_node, len(default_400_blocks) - 1)

        await disconnect_all_and_reconnect(wallet_server, full_node_server)

        # Tests a long reorg
        for block in default_1000_blocks:
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(block))

        log.info(f"wallet node height is {wallet_node.wallet_state_manager.blockchain._peak_height}")
        await time_out_assert(600, wallet_height_at_least, True, wallet_node, len(default_1000_blocks) - 1)

        await disconnect_all_and_reconnect(wallet_server, full_node_server)

        # Tests a short reorg
        num_blocks = 30
        blocks_reorg = bt.get_consecutive_blocks(num_blocks, block_list_input=default_1000_blocks[:-5])

        for i in range(1, len(blocks_reorg)):
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(blocks_reorg[i]))

        await time_out_assert(
            600, wallet_height_at_least, True, wallet_node, len(default_1000_blocks) + num_blocks - 5 - 1
        )

    @pytest.mark.asyncio
    async def test_wallet_reorg_sync(self, wallet_node_simulator, default_400_blocks):
        num_blocks = 5
        full_nodes, wallets = wallet_node_simulator
        full_node_api = full_nodes[0]
        wallet_node, server_2 = wallets[0]
        fn_server = full_node_api.full_node.server
        wsm: WalletStateManager = wallet_node.wallet_state_manager
        wallet = wsm.main_wallet
        ph = await wallet.get_new_puzzlehash()

        await server_2.start_client(PeerInfo(self_hostname, uint16(fn_server._port)), None)

        # Insert 400 blocks
        for block in default_400_blocks:
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(block))

        # Farm few more with reward
        for i in range(0, num_blocks):
            await full_node_api.farm_new_transaction_block(FarmNewBlockProtocol(ph))

        # Confirm we have the funds
        funds = sum(
            [calculate_pool_reward(uint32(i)) + calculate_base_farmer_reward(uint32(i)) for i in range(1, num_blocks)]
        )

        await time_out_assert(5, wallet.get_confirmed_balance, funds)

        async def get_tx_count(wallet_id):
            txs = await wsm.get_all_transactions(wallet_id)
            return len(txs)

        await time_out_assert(5, get_tx_count, 2 * (num_blocks - 1), 1)

        # Reorg blocks that carry reward
        num_blocks = 30
        blocks_reorg = bt.get_consecutive_blocks(num_blocks, block_list_input=default_400_blocks[:-5])

        for block in blocks_reorg[-30:]:
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(block))

        await time_out_assert(5, get_tx_count, 0, 1)
        await time_out_assert(5, wallet.get_confirmed_balance, 0)

    @pytest.mark.asyncio
    async def test_wallet_reorg_get_coinbase(self, wallet_node_simulator, default_400_blocks):
        full_nodes, wallets = wallet_node_simulator
        full_node_api = full_nodes[0]
        wallet_node, server_2 = wallets[0]
        fn_server = full_node_api.full_node.server
        wsm = wallet_node.wallet_state_manager
        wallet = wallet_node.wallet_state_manager.main_wallet
        ph = await wallet.get_new_puzzlehash()

        await server_2.start_client(PeerInfo(self_hostname, uint16(fn_server._port)), None)

        # Insert 400 blocks
        for block in default_400_blocks:
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(block))

        # Reorg blocks that carry reward
        num_blocks_reorg = 30
        blocks_reorg = bt.get_consecutive_blocks(num_blocks_reorg, block_list_input=default_400_blocks[:-5])

        for block in blocks_reorg[:-5]:
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(block))

        async def get_tx_count(wallet_id):
            txs = await wsm.get_all_transactions(wallet_id)
            return len(txs)

        await time_out_assert(10, get_tx_count, 0, 1)

        num_blocks_reorg_1 = 40
        blocks_reorg_1 = bt.get_consecutive_blocks(
            1, pool_reward_puzzle_hash=ph, farmer_reward_puzzle_hash=ph, block_list_input=blocks_reorg[:-30]
        )
        blocks_reorg_2 = bt.get_consecutive_blocks(num_blocks_reorg_1, block_list_input=blocks_reorg_1)

        for block in blocks_reorg_2[-41:]:
            await full_node_api.full_node.respond_block(full_node_protocol.RespondBlock(block))

        await disconnect_all_and_reconnect(server_2, fn_server)

        # Confirm we have the funds
        funds = calculate_pool_reward(uint32(len(blocks_reorg_1))) + calculate_base_farmer_reward(
            uint32(len(blocks_reorg_1))
        )

        await time_out_assert(10, get_tx_count, 2, 1)
        await time_out_assert(10, wallet.get_confirmed_balance, funds)

    @pytest.mark.asyncio
    async def test_wallet_wp_backwards_comp(self, two_nodes_two_wallets, default_1000_blocks):
        full_nodes, wallets = two_nodes_two_wallets
        blocks: List[FullBlock] = default_1000_blocks
        full_node_1, full_node_2 = full_nodes
        wallet_1, wallet_2 = wallets
        server_1 = full_node_1.full_node.server
        server_2 = full_node_2.full_node.server
        wallet_node_1, wallet_server_1 = wallet_1
        wallet_node_2, wallet_server_2 = wallet_2
        # no capabilities
        server_2.capabilities = [(uint16(Capability.BASE.value), "1")]

        for block in blocks[:800]:
            await full_node_1.full_node.respond_block(full_node_protocol.RespondBlock(block))
            await full_node_2.full_node.respond_block(full_node_protocol.RespondBlock(block))

        await wallet_server_1.start_client(PeerInfo(self_hostname, uint16(server_1._port)), None)
        await wallet_server_2.start_client(PeerInfo(self_hostname, uint16(server_2._port)), None)

        # The second node should eventually catch up to the first one, and have the
        # same tip at height num_blocks - 1.
        await time_out_assert(600, wallet_height_at_least, True, wallet_node_1, 799)
        await time_out_assert(600, wallet_height_at_least, True, wallet_node_2, 799)
