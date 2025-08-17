#!/usr/bin/env python3
"""
Shopify-like E-commerce Data Generator

Generates realistic e-commerce order data that mimics Shopify API responses,
including orders that naturally create exceptions for testing the E²A system.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from faker import Faker
from faker.providers import internet, person, address, company, phone_number
import uuid


class ShopifyDataGenerator:
    """Generates realistic Shopify-like e-commerce data with natural exception scenarios."""
    
    def __init__(self, seed: Optional[int] = None):
        """Initialize the generator with optional seed for reproducibility."""
        if seed:
            random.seed(seed)
            Faker.seed(seed)
        
        # Initialize faker with multiple locales for diversity
        self.fake = Faker(['en_US', 'en_CA', 'en_GB', 'en_AU'])
        
        # Product categories and realistic products
        self.product_categories = {
            'electronics': [
                {'name': 'iPhone 15 Pro', 'price_range': (999, 1199), 'weight': 0.187},
                {'name': 'Samsung Galaxy S24', 'price_range': (799, 999), 'weight': 0.168},
                {'name': 'MacBook Air M3', 'price_range': (1099, 1599), 'weight': 1.24},
                {'name': 'iPad Pro 12.9"', 'price_range': (1099, 1899), 'weight': 0.682},
                {'name': 'AirPods Pro', 'price_range': (249, 299), 'weight': 0.056},
                {'name': 'Apple Watch Series 9', 'price_range': (399, 799), 'weight': 0.042},
            ],
            'clothing': [
                {'name': 'Premium Cotton T-Shirt', 'price_range': (29, 59), 'weight': 0.2},
                {'name': 'Designer Jeans', 'price_range': (89, 199), 'weight': 0.6},
                {'name': 'Wool Sweater', 'price_range': (79, 149), 'weight': 0.4},
                {'name': 'Running Shoes', 'price_range': (99, 249), 'weight': 0.8},
                {'name': 'Winter Jacket', 'price_range': (149, 399), 'weight': 1.2},
            ],
            'home_garden': [
                {'name': 'Smart Home Hub', 'price_range': (99, 199), 'weight': 0.5},
                {'name': 'Coffee Maker', 'price_range': (79, 299), 'weight': 3.2},
                {'name': 'Vacuum Cleaner', 'price_range': (199, 599), 'weight': 6.8},
                {'name': 'Garden Tool Set', 'price_range': (49, 129), 'weight': 2.1},
            ],
            'books': [
                {'name': 'Bestselling Novel', 'price_range': (12, 28), 'weight': 0.3},
                {'name': 'Technical Manual', 'price_range': (39, 89), 'weight': 0.8},
                {'name': 'Cookbook', 'price_range': (19, 45), 'weight': 0.6},
            ]
        }
        
        # Shipping methods with realistic delivery times
        self.shipping_methods = [
            {'name': 'Standard Shipping', 'cost_range': (5, 15), 'days_range': (5, 8)},
            {'name': 'Express Shipping', 'cost_range': (15, 25), 'days_range': (2, 3)},
            {'name': 'Overnight Shipping', 'cost_range': (25, 45), 'days_range': (1, 1)},
            {'name': 'Free Shipping', 'cost_range': (0, 0), 'days_range': (7, 10)},
        ]
        
        # Exception scenarios with realistic probabilities
        self.exception_scenarios = [
            {
                'type': 'DELIVERY_DELAY',
                'probability': 0.05,  # 5% of orders
                'description': 'Package delayed due to weather/carrier issues',
                'severity_weights': {'LOW': 0.4, 'MEDIUM': 0.5, 'HIGH': 0.1}
            },
            {
                'type': 'ADDRESS_INVALID',
                'probability': 0.02,  # 2% of orders
                'description': 'Invalid or incomplete shipping address',
                'severity_weights': {'MEDIUM': 0.6, 'HIGH': 0.4}
            },
            {
                'type': 'PAYMENT_FAILED',
                'probability': 0.015,  # 1.5% of orders
                'description': 'Payment processing failed or declined',
                'severity_weights': {'HIGH': 0.7, 'CRITICAL': 0.3}
            },
            {
                'type': 'INVENTORY_SHORTAGE',
                'probability': 0.025,  # 2.5% of orders
                'description': 'Product out of stock after order placement',
                'severity_weights': {'MEDIUM': 0.5, 'HIGH': 0.5}
            },
            {
                'type': 'DAMAGED_PACKAGE',
                'probability': 0.008,  # 0.8% of orders
                'description': 'Package damaged during shipping',
                'severity_weights': {'MEDIUM': 0.3, 'HIGH': 0.7}
            },
            {
                'type': 'CUSTOMER_UNAVAILABLE',
                'probability': 0.03,  # 3% of orders
                'description': 'Customer not available for delivery',
                'severity_weights': {'LOW': 0.7, 'MEDIUM': 0.3}
            }
        ]
    
    def generate_customer(self) -> Dict[str, Any]:
        """Generate a realistic customer profile."""
        first_name = self.fake.first_name()
        last_name = self.fake.last_name()
        
        # Generate realistic email with common domains (avoid example.com/org)
        email_domains = [
            'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com',
            'icloud.com', 'protonmail.com', 'live.com', 'msn.com', 'comcast.net'
        ]
        email_username = f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}"
        email = f"{email_username}@{random.choice(email_domains)}"
        
        return {
            'id': str(uuid.uuid4()),
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'phone': self.fake.phone_number(),
            'created_at': self.fake.date_time_between(start_date='-2y', end_date='now').isoformat(),
            'orders_count': random.randint(1, 15),
            'total_spent': round(random.uniform(50, 2500), 2),
            'verified_email': random.choice([True, True, True, False]),  # 75% verified
            'marketing_opt_in': random.choice([True, False])
        }
    
    def generate_address(self, customer: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a realistic shipping address."""
        # Sometimes use obviously problematic addresses for exceptions
        if random.random() < 0.03:  # 3% chance of problematic address
            return self._generate_problematic_address()
        
        return {
            'first_name': customer['first_name'],
            'last_name': customer['last_name'],
            'company': self.fake.company() if random.random() < 0.3 else None,
            'address1': self.fake.street_address(),
            'address2': self.fake.secondary_address() if random.random() < 0.2 else None,
            'city': self.fake.city(),
            'province': self.fake.state_abbr(),
            'country': 'United States',
            'zip': self.fake.zipcode(),
            'phone': customer['phone']
        }
    
    def _generate_problematic_address(self) -> Dict[str, Any]:
        """Generate addresses that will cause delivery exceptions."""
        problematic_scenarios = [
            {
                'address1': '123 Nonexistent Street',
                'city': 'Nowhere',
                'zip': '00000'
            },
            {
                'address1': 'PO Box 999999',  # Invalid PO Box
                'city': self.fake.city(),
                'zip': '99999'
            },
            {
                'address1': self.fake.street_address(),
                'city': self.fake.city(),
                'zip': 'INVALID'  # Invalid zip code
            }
        ]
        
        base_address = random.choice(problematic_scenarios)
        return {
            'first_name': self.fake.first_name(),
            'last_name': self.fake.last_name(),
            'company': None,
            'address2': None,
            'province': self.fake.state_abbr(),
            'country': 'United States',
            'phone': self.fake.phone_number(),
            **base_address
        }
    
    def generate_product_variant(self, category: str = None) -> Dict[str, Any]:
        """Generate a realistic product variant."""
        if not category:
            category = random.choice(list(self.product_categories.keys()))
        
        product_template = random.choice(self.product_categories[category])
        
        # Generate variant details
        variant_id = str(uuid.uuid4())
        price = round(random.uniform(*product_template['price_range']), 2)
        
        # Add realistic variant options
        variant_options = {}
        if category == 'clothing':
            variant_options = {
                'size': random.choice(['XS', 'S', 'M', 'L', 'XL', 'XXL']),
                'color': random.choice(['Black', 'White', 'Navy', 'Gray', 'Red', 'Blue'])
            }
        elif category == 'electronics':
            variant_options = {
                'storage': random.choice(['64GB', '128GB', '256GB', '512GB', '1TB']),
                'color': random.choice(['Space Gray', 'Silver', 'Gold', 'Blue', 'Purple'])
            }
        
        return {
            'id': variant_id,
            'product_id': str(uuid.uuid4()),
            'title': product_template['name'],
            'price': str(price),
            'sku': f"{category.upper()[:3]}-{random.randint(1000, 9999)}",
            'inventory_quantity': random.randint(0, 100),
            'weight': product_template['weight'],
            'requires_shipping': True,
            'taxable': True,
            'option1': variant_options.get('size') or variant_options.get('storage'),
            'option2': variant_options.get('color'),
            'category': category
        }
    
    def generate_line_item(self, variant: Dict[str, Any] = None) -> Dict[str, Any]:
        """Generate a realistic order line item."""
        if not variant:
            variant = self.generate_product_variant()
        
        quantity = random.choices([1, 2, 3, 4, 5], weights=[50, 25, 15, 7, 3])[0]
        price = float(variant['price'])
        
        return {
            'id': str(uuid.uuid4()),
            'variant_id': variant['id'],
            'product_id': variant['product_id'],
            'title': variant['title'],
            'quantity': quantity,
            'price': str(price),
            'total_discount': '0.00',
            'sku': variant['sku'],
            'weight': variant['weight'],
            'requires_shipping': variant['requires_shipping'],
            'taxable': variant['taxable'],
            'name': f"{variant['title']} - {variant['option1']}" + (f" / {variant['option2']}" if variant['option2'] else "")
        }
    
    def generate_order(self, customer: Dict[str, Any] = None) -> Dict[str, Any]:
        """Generate a complete realistic order."""
        if not customer:
            customer = self.generate_customer()
        
        order_id = str(uuid.uuid4())
        order_number = random.randint(1000, 99999)
        
        # Generate line items (1-4 items per order typically)
        num_items = random.choices([1, 2, 3, 4], weights=[40, 35, 20, 5])[0]
        line_items = []
        subtotal = 0
        
        for _ in range(num_items):
            line_item = self.generate_line_item()
            line_items.append(line_item)
            subtotal += float(line_item['price']) * line_item['quantity']
        
        # Calculate shipping
        shipping_method = random.choice(self.shipping_methods)
        shipping_cost = random.uniform(*shipping_method['cost_range'])
        if subtotal > 75:  # Free shipping over $75
            shipping_cost = 0
            shipping_method = {'name': 'Free Shipping', 'days_range': (5, 7)}
        
        # Calculate tax (realistic US sales tax)
        tax_rate = random.uniform(0.06, 0.11)  # 6-11% tax
        tax_amount = subtotal * tax_rate
        
        total_price = subtotal + shipping_cost + tax_amount
        
        # Generate timestamps
        created_at = self.fake.date_time_between(start_date='-30d', end_date='now')
        processed_at = created_at + timedelta(minutes=random.randint(1, 30))
        
        # Estimated delivery
        delivery_days = random.randint(*shipping_method['days_range'])
        estimated_delivery = created_at + timedelta(days=delivery_days)
        
        # Generate shipping address
        shipping_address = self.generate_address(customer)
        
        order = {
            'id': order_id,
            'order_number': order_number,
            'name': f"#{order_number}",
            'email': customer['email'],
            'created_at': created_at.isoformat(),
            'updated_at': processed_at.isoformat(),
            'processed_at': processed_at.isoformat(),
            'customer': customer,
            'shipping_address': shipping_address,
            'billing_address': shipping_address,  # Same as shipping for simplicity
            'line_items': line_items,
            'subtotal_price': str(round(subtotal, 2)),
            'total_tax': str(round(tax_amount, 2)),
            'total_price': str(round(total_price, 2)),
            'currency': 'USD',
            'financial_status': 'paid',
            'fulfillment_status': self._determine_fulfillment_status(created_at),
            'shipping_lines': [{
                'title': shipping_method['name'],
                'price': str(round(shipping_cost, 2)),
                'code': shipping_method['name'].upper().replace(' ', '_')
            }],
            'order_status_url': f"https://shop.example.com/orders/{order_id}/status",
            'tags': self._generate_order_tags(),
            'note': self._generate_order_note() if random.random() < 0.1 else None,
            'estimated_delivery_date': estimated_delivery.isoformat()
        }
        
        return order
    
    def _determine_fulfillment_status(self, created_at: datetime) -> str:
        """Determine realistic fulfillment status based on order age."""
        age_hours = (datetime.now() - created_at).total_seconds() / 3600
        
        if age_hours < 2:
            return random.choice(['pending', 'pending', 'pending', 'fulfilled'])
        elif age_hours < 24:
            return random.choice(['pending', 'fulfilled', 'fulfilled'])
        elif age_hours < 72:
            return random.choice(['fulfilled', 'fulfilled', 'shipped'])
        else:
            return random.choice(['fulfilled', 'shipped', 'delivered'])
    
    def _generate_order_tags(self) -> str:
        """Generate realistic order tags."""
        possible_tags = [
            'first-time-customer', 'repeat-customer', 'high-value', 'express-shipping',
            'gift-order', 'bulk-order', 'vip-customer', 'mobile-order', 'web-order'
        ]
        
        num_tags = random.randint(0, 3)
        if num_tags == 0:
            return ""
        
        return ", ".join(random.sample(possible_tags, num_tags))
    
    def _generate_order_note(self) -> str:
        """Generate realistic order notes."""
        notes = [
            "Please leave package at front door",
            "Gift wrapping requested",
            "Delivery instructions: Ring doorbell twice",
            "Customer requested expedited processing",
            "Special handling required - fragile items",
            "Corporate order - invoice separately"
        ]
        return random.choice(notes)
    
    def should_create_problematic_order(self) -> Optional[Dict[str, Any]]:
        """Determine if this order should have problems that will trigger exceptions."""
        # 20% chance of creating a problematic order
        if random.random() < 0.20:
            scenario = random.choice(self.exception_scenarios)
            
            # Select severity based on weights
            severities = list(scenario['severity_weights'].keys())
            weights = list(scenario['severity_weights'].values())
            severity = random.choices(severities, weights=weights)[0]
            
            return {
                'type': scenario['type'],
                'severity': severity,
                'description': scenario['description'],
                'should_trigger_exception': True
            }
        
        return None
    
    def generate_order_with_problems(self) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Generate an order and determine if it should have problems."""
        order = self.generate_order()
        problem = self.should_create_problematic_order()
        
        # If there's a problem, modify the order to reflect realistic issues
        if problem:
            if problem['type'] == 'DELIVERY_DELAY':
                # Make delivery date unrealistic (too far in future or past due)
                original_date = datetime.fromisoformat(order['estimated_delivery_date'])
                if random.choice([True, False]):
                    # Past due delivery
                    delayed_date = original_date - timedelta(days=random.randint(1, 5))
                    order['fulfillment_status'] = 'delayed'
                else:
                    # Unrealistic future delivery
                    delayed_date = original_date + timedelta(days=random.randint(10, 30))
                order['estimated_delivery_date'] = delayed_date.isoformat()
                
            elif problem['type'] == 'PAYMENT_FAILED':
                order['financial_status'] = 'pending'
                order['payment_issues'] = True
                
            elif problem['type'] == 'INVENTORY_SHORTAGE':
                # Mark some items as having low inventory
                for item in order['line_items']:
                    if random.random() < 0.5:  # 50% chance this item has inventory issues
                        item['inventory_shortage'] = True
                        item['available_quantity'] = random.randint(0, 2)
                        
            elif problem['type'] == 'ADDRESS_INVALID':
                # Create problematic address
                order['shipping_address'] = self._generate_problematic_address()
                
            elif problem['type'] == 'DAMAGED_PACKAGE':
                # Add damage indicators
                order['package_condition'] = 'damaged'
                order['damage_report'] = 'Package shows signs of damage during transit'
                
            elif problem['type'] == 'CUSTOMER_UNAVAILABLE':
                # Add delivery attempt failures
                order['delivery_attempts'] = random.randint(2, 4)
                order['delivery_status'] = 'failed_delivery'
        
        return order, problem


# Example usage and testing
if __name__ == "__main__":
    generator = ShopifyDataGenerator(seed=42)
    
    # Generate some sample orders
    print("Generating sample orders with potential exceptions...")
    
    for i in range(10):
        order, exception = generator.generate_order_with_exception()
        
        print(f"\nOrder #{order['order_number']}:")
        print(f"  Customer: {order['customer']['first_name']} {order['customer']['last_name']}")
        print(f"  Email: {order['email']}")
        print(f"  Total: ${order['total_price']}")
        print(f"  Items: {len(order['line_items'])}")
        print(f"  Status: {order['fulfillment_status']}")
        
        if exception:
            print(f"  🚨 EXCEPTION: {exception['type']} ({exception['severity']})")
            print(f"     {exception['description']}")
        else:
            print("  ✅ No exceptions")
