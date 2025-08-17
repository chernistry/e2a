#!/usr/bin/env python3
"""
DLQ Replay Script - Reprocess failed events after bug fixes.

This script fetches failed events from the Dead Letter Queue and attempts
to reprocess them using the current (fixed) code.
"""

import asyncio
import json
import sys
import os
from typing import Dict, Any
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.storage.dlq import fetch_batch, mark_retry_attempt
from app.storage.models import DLQ
from app.routes.ingest import _process_event
from app.schemas.ingest import ShopifyOrderEvent, WMSEvent, CarrierEvent
from fastapi import Request


class MockRequest:
    """Mock request object for DLQ replay."""
    
    def __init__(self, tenant: str, correlation_id: str):
        self.state = type('obj', (object,), {'correlation_id': correlation_id})()
        self.headers = {'X-Tenant-Id': tenant}
        # Add scope for FastAPI compatibility
        self.scope = {
            'type': 'http',
            'method': 'POST',
            'headers': [(b'x-tenant-id', tenant.encode())],
            'query_string': b'',
            'path': '/ingest/replay'
        }
        # Add other required attributes
        self.url = type('obj', (object,), {
            'path': '/ingest/replay',
            'scheme': 'http',
            'hostname': 'localhost'
        })()
        self.method = 'POST'


async def replay_dlq_batch(batch_size: int = 10, max_batches: int = None) -> Dict[str, int]:
    """
    Replay DLQ items in batches.
    
    Args:
        batch_size: Number of items to process per batch
        max_batches: Maximum number of batches to process (None = all)
        
    Returns:
        Dictionary with processing statistics
    """
    stats = {
        'processed': 0,
        'successful': 0,
        'failed': 0,
        'skipped': 0
    }
    
    batch_count = 0
    
    # Use environment DATABASE_URL
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL not found in environment variables")
    
    print(f"🔗 Connecting to database: {db_url.split('@')[1] if '@' in db_url else 'localhost'}")
    
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with async_session() as db:
            while True:
                # Check batch limit
                if max_batches and batch_count >= max_batches:
                    print(f"✅ Reached batch limit ({max_batches})")
                    break
                
                # Fetch batch of DLQ items
                dlq_items = await fetch_batch(db, limit=batch_size)
                
                if not dlq_items:
                    print("✅ No more DLQ items to process")
                    break
                
                print(f"\n📦 Processing batch {batch_count + 1} ({len(dlq_items)} items)")
                
                for dlq_item in dlq_items:
                    stats['processed'] += 1
                    
                    try:
                        # Parse the original payload
                        payload = dlq_item.payload
                        
                        # Determine event type and create appropriate schema
                        event_data = None
                        source = payload.get('source', '').lower()
                        
                        if source == 'shopify':
                            event_data = ShopifyOrderEvent(**payload)
                        elif source == 'wms':
                            event_data = WMSEvent(**payload)
                        elif source == 'carrier':
                            event_data = CarrierEvent(**payload)
                        else:
                            print(f"⚠️  Unknown event source: {source}")
                            await mark_retry_attempt(db, dlq_item, success=False, error_message=f"Unknown source: {source}")
                            stats['skipped'] += 1
                            continue
                        
                        # Create mock request
                        mock_request = MockRequest(
                            tenant=dlq_item.tenant,
                            correlation_id=dlq_item.correlation_id or f"dlq-replay-{dlq_item.id}"
                        )
                        
                        # Attempt to reprocess the event
                        result = await _process_event(event_data, mock_request, db)
                        
                        # Mark as successful
                        await mark_retry_attempt(db, dlq_item, success=True)
                        stats['successful'] += 1
                        
                        print(f"✅ Successfully reprocessed DLQ item {dlq_item.id} (order: {payload.get('order_id', 'N/A')})")
                        
                    except Exception as e:
                        # Mark as failed with new error message
                        error_msg = f"Replay failed: {str(e)}"
                        await mark_retry_attempt(db, dlq_item, success=False, error_message=error_msg)
                        stats['failed'] += 1
                        
                        print(f"❌ Failed to reprocess DLQ item {dlq_item.id}: {e}")
                
                # Commit the batch
                await db.commit()
                batch_count += 1
                
                print(f"📊 Batch {batch_count} completed - Success: {stats['successful']}, Failed: {stats['failed']}, Skipped: {stats['skipped']}")
                
                # Small delay between batches
                await asyncio.sleep(0.5)
                
    except Exception as e:
        print(f"❌ Critical error during DLQ replay: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await engine.dispose()
    
    return stats


async def check_dlq_status():
    """Check current DLQ status before replay."""
    
    db_url = os.getenv('DATABASE_URL')
    engine = create_async_engine(db_url)
    
    try:
        async with engine.begin() as conn:
            # Get status breakdown
            result = await conn.execute(text('''
                SELECT 
                    status, 
                    COUNT(*) as count,
                    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
                FROM dlq 
                GROUP BY status 
                ORDER BY count DESC
            '''))
            
            print("📊 Current DLQ Status:")
            for row in result:
                print(f"  • {row[0]}: {row[1]} ({row[2]:.1f}%)")
            
            # Get error breakdown for pending items
            result = await conn.execute(text('''
                SELECT 
                    error_class, 
                    COUNT(*) as count
                FROM dlq 
                WHERE status = 'PENDING'
                GROUP BY error_class 
                ORDER BY count DESC
            '''))
            
            print("\n🔍 Pending Error Types:")
            for row in result:
                print(f"  • {row[0]}: {row[1]}")
            
            # Get total pending count
            result = await conn.execute(text("SELECT COUNT(*) FROM dlq WHERE status = 'PENDING'"))
            pending_count = result.scalar()
            
            return pending_count
            
    except Exception as e:
        print(f"❌ Could not check DLQ status: {e}")
        return 0
    finally:
        await engine.dispose()


async def main():
    """Main function for DLQ replay."""
    print("🔄 DLQ Replay Script")
    print("=" * 50)
    
    # Check current DLQ status
    pending_count = await check_dlq_status()
    
    if pending_count == 0:
        print("✅ No pending DLQ items to process")
        return
    
    print(f"\n📋 Found {pending_count} pending DLQ items")
    
    # Ask for confirmation
    print("\n🤔 Replay Options:")
    print("1. Replay small batch (20 items) - for testing")
    print("2. Replay all items")
    print("3. Cancel")
    
    choice = input("\nEnter your choice (1/2/3): ").strip()
    
    if choice == "1":
        max_batches = 1
        batch_size = 20
        print(f"🧪 Testing with {batch_size} items...")
    elif choice == "2":
        max_batches = None
        batch_size = 50
        print(f"🚀 Processing all {pending_count} items...")
    else:
        print("❌ Replay cancelled")
        return
    
    # Start replay process
    start_time = datetime.now()
    
    try:
        stats = await replay_dlq_batch(batch_size=batch_size, max_batches=max_batches)
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        print("\n" + "=" * 50)
        print("🎉 DLQ Replay Completed!")
        print(f"⏱️  Duration: {duration}")
        print(f"📊 Final Statistics:")
        print(f"   • Processed: {stats['processed']}")
        print(f"   • Successful: {stats['successful']}")
        print(f"   • Failed: {stats['failed']}")
        print(f"   • Skipped: {stats['skipped']}")
        
        if stats['processed'] > 0:
            success_rate = (stats['successful'] / stats['processed']) * 100
            print(f"   • Success Rate: {success_rate:.1f}%")
        
        # Check final DLQ status
        print("\n🔍 Final DLQ Status:")
        await check_dlq_status()
        
    except Exception as e:
        print(f"❌ Replay process failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
