"""
Multi-Gateway CC Checker - Gateway Package
===========================================
All payment gateways integrated here
"""

from .stripe import StripeGateway, STRIPE_VERSIONS
from .razorpay import RazorpayGateway
from .adyen import AdyenGateway
from .paypal import PayPalGateway
from .shopify import ShopifyGateway

__all__ = [
    'StripeGateway', 'RazorpayGateway', 'AdyenGateway',
    'PayPalGateway', 'ShopifyGateway', 'STRIPE_VERSIONS'
]

GATEWAYS = {
    'stripe': {
        'class': StripeGateway, 'name': 'Stripe', 'display_name': 'Stripe',
        'working': True, 'description': 'Stripe - 10 payment link versions',
        'supported_cards': ['visa', 'mastercard', 'amex', 'discover', 'jcb'],
        'versions': list(STRIPE_VERSIONS.keys())
    },
    'razorpay': {
        'class': RazorpayGateway, 'name': 'Razorpay', 'display_name': 'Razorpay',
        'working': True, 'description': 'Razorpay - mulearn.org flow',
        'supported_cards': ['visa', 'mastercard', 'amex', 'jcb', 'rupay'],
        'versions': [1]
    },
    'adyen': {
        'class': AdyenGateway, 'name': 'Adyen', 'display_name': 'Adyen (Picsart)',
        'working': True, 'description': 'Adyen - Picsart.com checkout',
        'supported_cards': ['visa', 'mastercard'],
        'versions': [1]
    },
    'paypal': {
        'class': PayPalGateway, 'name': 'PayPal', 'display_name': 'PayPal Commerce',
        'working': True, 'description': 'PayPal - GraphQL mutation flow',
        'supported_cards': ['visa', 'mastercard', 'amex', 'discover'],
        'versions': [1]
    },
    'shopify': {
        'class': ShopifyGateway, 'name': 'Shopify', 'display_name': 'Shopify',
        'working': True, 'description': 'Shopify - GraphQL checkout flow',
        'supported_cards': ['visa', 'mastercard', 'amex', 'discover'],
        'versions': [1]
    }
}

def get_gateway(name: str):
    gateway_info = GATEWAYS.get(name.lower())
    if gateway_info and gateway_info.get('working', False):
        return gateway_info['class']
    return None

def get_all_gateways():
    return list(GATEWAYS.keys())

def get_working_gateways():
    return [name for name, info in GATEWAYS.items() if info.get('working', False)]

def get_gateway_info(name: str):
    return GATEWAYS.get(name.lower())

def get_supported_cards(gateway_name: str):
    info = GATEWAYS.get(gateway_name.lower())
    if info:
        return info.get('supported_cards', [])
    return []

def get_gateway_versions(gateway_name: str):
    info = GATEWAYS.get(gateway_name.lower())
    if info:
        return info.get('versions', [1])
    return [1]
