#!/usr/bin/env python3
"""
KhfyPay Client - Simple Implementation
"""

import aiohttp
import logging

logger = logging.getLogger(__name__)

class KhfyPayClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://panel.khfy-store.com/api_v2"
    
    async def create_transaction(self, product_code, target, ref_id):
        """Create transaction in KhfyPay"""
        try:
            params = {
                "produk": product_code,
                "tujuan": target,
                "reff_id": ref_id,
                "api_key": self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/trx", params=params) as response:
                    return await response.json()
        except Exception as e:
            logger.error(f"KhfyPay API error: {e}")
            return None

def get_khfypay_client():
    """Get KhfyPay client instance"""
    import config
    api_key = getattr(config, 'KHFYPAY_API_KEY', '')
    return KhfyPayClient(api_key)
