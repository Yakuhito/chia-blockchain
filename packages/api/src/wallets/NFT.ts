import Wallet from '../services/Wallet';

export default class NFTWallet extends Wallet {
  async getNfts(walletId: number) {
    return this.command('nft_get_nfts', {
      walletId,
    });
  }

  async transferNft(
    walletId: number,
    nftCoinId: string,
    targetAddress: string
  ) {
    return this.command('nft_transfer_nft', {
      walletId,
      nftCoinId,
      targetAddress,
    });
  }

  async receiveNft(walletId: number, spendBundle: any, fee: number) {
    return this.command('nft_receive_nft', {
      walletId,
      spendBundle,
      fee,
    });
  }
}
