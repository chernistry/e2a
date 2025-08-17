#!/usr/bin/env python3

# ==== INVOICE GENERATION MANAGEMENT SCRIPT ==== #

"""
Invoice Generation Management Script for Octup E²A

This script generates missing invoices for completed orders with comprehensive
validation and audit capabilities. It can be run manually or scheduled to ensure
all completed orders have corresponding invoices.

Features:
- Missing invoice detection and generation
- Tenant-specific backfill operations
- Dry-run mode for testing and validation
- Comprehensive validation and audit logging
- Configurable lookback periods
- Multi-tenant support with isolation
- Invoice amount calculation and validation
- Order completion verification

Usage:
    python generate_invoices.py [--tenant TENANT] [--lookback-hours HOURS] [--dry-run]
    python generate_invoices.py --backfill --tenant TENANT [--days-back DAYS] [--dry-run]

Examples:
    # Generate missing invoices for all tenants (last 7 days)
    python generate_invoices.py
    
    # Generate for specific tenant (last 7 days)
    python generate_invoices.py --tenant demo-3pl
    
    # Custom lookback period (last 24 hours)
    python generate_invoices.py --lookback-hours 24
    
    # Backfill invoices for specific tenant (last 30 days)
    python generate_invoices.py --backfill --tenant demo-3pl --days-back 30
    
    # Dry run to preview operations
    python generate_invoices.py --dry-run

Dependencies:
    - Database connection (PostgreSQL)
    - Invoice generation service
    - Order event models and schemas
    - Logging and observability components

Author: E²A Team
Version: 1.0.0
"""

import asyncio
import argparse
import sys
from pathlib import Path
from typing import Optional, List

# Add the root directory to Python path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from app.storage.db import get_session
from app.services.invoice_generator import generate_missing_invoices, backfill_invoices_for_tenant
from app.observability.logging import ContextualLogger


logger = ContextualLogger(__name__)


# ==== INVOICE GENERATION COMMANDS ==== #


async def generate_invoices_command(
    tenant: Optional[str] = None,
    lookback_hours: int = 168,
    dry_run: bool = False
) -> None:
    """
    Generate missing invoices for completed orders within specified timeframe.
    
    This function identifies orders that have completed their lifecycle but lack
    corresponding invoices. It processes completed orders within the specified
    lookback period and generates invoices with comprehensive validation.
    
    Args:
        tenant (Optional[str]): Specific tenant to process (None for all tenants)
        lookback_hours (int): How far back to look for completed orders (default: 168h = 7 days)
        dry_run (bool): If True, simulate operations without creating actual invoices
        
    Raises:
        Exception: If invoice generation fails or database errors occur
        
    Note:
        The lookback period is calculated from the current timestamp and includes
        orders that have completed all required events (order_paid, pick_completed,
        pack_completed, ship_label_printed).
    """
    logger.info(f"Starting invoice generation (lookback: {lookback_hours}h, tenant: {tenant or 'all'})")
    
    if dry_run:
        logger.info("DRY RUN MODE - No invoices will be created")
        logger.info("Would generate invoices for completed orders within lookback period")
        return
    
    async with get_session() as db:
        try:
            # Generate missing invoices through the service layer
            invoices = await generate_missing_invoices(
                db, tenant, lookback_hours
            )
            
            logger.info(f"Successfully generated {len(invoices)} invoices")
            
            # Print comprehensive summary
            if invoices:
                total_amount = sum(inv.amount_cents for inv in invoices)
                logger.info(f"Total invoice amount: ${total_amount/100:.2f}")
                
                # Log individual invoice details
                for invoice in invoices:
                    logger.info(
                        f"  {invoice.invoice_number}: {invoice.order_id} - "
                        f"${invoice.amount_cents/100:.2f}"
                    )
                    
                # Log summary statistics
                logger.info(f"Invoice generation completed successfully")
                logger.info(f"  - Total invoices: {len(invoices)}")
                logger.info(f"  - Total amount: ${total_amount/100:.2f}")
                logger.info(f"  - Average amount: ${(total_amount/len(invoices))/100:.2f}")
            else:
                logger.info("No missing invoices found for the specified criteria")
            
        except Exception as e:
            logger.error(f"Failed to generate invoices: {str(e)}")
            raise


async def backfill_invoices_command(
    tenant: str,
    days_back: int = 30,
    dry_run: bool = False
) -> None:
    """
    Perform comprehensive invoice backfill for specified tenant.
    
    This function performs historical invoice backfill for a specific tenant
    within the specified time period. It's useful for:
    - Initial system setup
    - Data migration scenarios
    - Correcting historical data gaps
    - Compliance and audit requirements
    
    Args:
        tenant (str): Tenant identifier for targeted backfill operations
        days_back (int): How many days back to perform backfill (default: 30 days)
        dry_run (bool): If True, simulate backfill without creating invoices
        
    Raises:
        Exception: If backfill operations fail or database errors occur
        
    Note:
        Backfill operations can be resource-intensive for large datasets.
        Consider running during off-peak hours and monitoring system performance.
    """
    logger.info(f"Starting invoice backfill for tenant '{tenant}' (days back: {days_back})")
    
    if dry_run:
        logger.info("DRY RUN MODE - No invoices will be created")
        logger.info(f"Would backfill invoices for tenant '{tenant}' going back {days_back} days")
        return
    
    async with get_session() as db:
        try:
            # Execute backfill through the service layer
            invoices = await backfill_invoices_for_tenant(
                db, tenant, days_back
            )
            
            logger.info(f"Successfully backfilled {len(invoices)} invoices for tenant '{tenant}'")
            
            # Print detailed backfill summary
            if invoices:
                total_amount = sum(inv.amount_cents for inv in invoices)
                logger.info(f"Total backfilled amount: ${total_amount/100:.2f}")
                
                # Group invoices by date for better reporting
                from collections import defaultdict
                date_groups = defaultdict(list)
                
                for invoice in invoices:
                    # Extract date from invoice creation timestamp
                    invoice_date = invoice.created_at.date() if hasattr(invoice, 'created_at') else 'Unknown'
                    date_groups[invoice_date].append(invoice)
                
                # Log grouped summary
                logger.info("Backfill summary by date:")
                for date, date_invoices in sorted(date_groups.items()):
                    date_amount = sum(inv.amount_cents for inv in date_invoices)
                    logger.info(f"  {date}: {len(date_invoices)} invoices, ${date_amount/100:.2f}")
                
                logger.info(f"Backfill completed successfully for tenant '{tenant}'")
                logger.info(f"  - Total invoices: {len(invoices)}")
                logger.info(f"  - Total amount: ${total_amount/100:.2f}")
                logger.info(f"  - Date range: {days_back} days back")
            else:
                logger.info(f"No invoices required for backfill in tenant '{tenant}'")
            
        except Exception as e:
            logger.error(f"Failed to backfill invoices for tenant '{tenant}': {str(e)}")
            raise


async def list_completed_orders_without_invoices(
    tenant: str = None,
    lookback_hours: int = 168
) -> None:
    """
    List completed orders that don't have invoices.
    
    Provides comprehensive audit of completed orders without
    corresponding invoices for operational transparency and
    compliance verification.
    
    Args:
        tenant (str): Specific tenant to check (None for all)
        lookback_hours (int): How far back to look for orders
    """
    logger.info(f"Checking for completed orders without invoices (lookback: {lookback_hours}h)")
    
    async with get_session() as db:
        from app.services.invoice_generator import InvoiceGeneratorService
        import datetime as dt
        
        generator = InvoiceGeneratorService()
        cutoff_time = dt.datetime.utcnow() - dt.timedelta(hours=lookback_hours)
        
        # Find completed orders
        completed_orders = await generator._find_completed_orders(
            db, tenant, cutoff_time
        )
        
        orders_without_invoices = []
        
        for order_info in completed_orders:
            existing_invoice = await generator._check_existing_invoice(
                db, order_info["tenant"], order_info["order_id"]
            )
            
            if not existing_invoice:
                orders_without_invoices.append(order_info)
        
        logger.info(f"Found {len(orders_without_invoices)} completed orders without invoices:")
        
        for order_info in orders_without_invoices:
            event_types = [e.event_type for e in order_info["events"]]
            logger.info(
                f"  {order_info['tenant']}/{order_info['order_id']}: "
                f"{len(order_info['events'])} events ({', '.join(set(event_types))})"
            )


# ==== MAIN ENTRY POINT ==== #


async def main():
    """
    Main function to orchestrate invoice generation operations.
    
    Parses command line arguments and executes the appropriate invoice
    generation or backfill command with proper error handling and logging.
    """
    parser = argparse.ArgumentParser(
        description="Generate missing invoices for completed orders in Octup E²A",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate missing invoices for all tenants (last 7 days)
  python generate_invoices.py
  
  # Generate for specific tenant with custom lookback
  python generate_invoices.py --tenant demo-3pl --lookback-hours 48
  
  # Backfill historical invoices for specific tenant
  python generate_invoices.py --backfill --tenant demo-3pl --days-back 90
  
  # Preview operations without making changes
  python generate_invoices.py --dry-run
        """
    )
    
    # Add command groups
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--backfill", 
        action="store_true",
        help="Enable backfill mode for historical invoice generation"
    )
    
    # Common arguments
    parser.add_argument(
        "--tenant", 
        type=str, 
        default=None,
        help="Specific tenant to process (default: all tenants)"
    )
    
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Simulate operations without creating actual invoices"
    )
    
    # Mode-specific arguments
    parser.add_argument(
        "--lookback-hours", 
        type=int, 
        default=168,
        help="Hours to look back for completed orders (default: 168 = 7 days)"
    )
    
    parser.add_argument(
        "--days-back", 
        type=int, 
        default=30,
        help="Days back for backfill operations (default: 30)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.backfill and not args.tenant:
        parser.error("--backfill requires --tenant to be specified")
    
    if args.lookback_hours < 1:
        parser.error("--lookback-hours must be at least 1")
    
    if args.days_back < 1:
        parser.error("--days-back must be at least 1")
    
    print("📄 Invoice Generation Management")
    print("=" * 40)
    print(f"Mode: {'Backfill' if args.backfill else 'Standard Generation'}")
    print(f"Tenant: {args.tenant or 'All tenants'}")
    print(f"Dry run: {'Yes' if args.dry_run else 'No'}")
    
    if args.backfill:
        print(f"Days back: {args.days_back}")
    else:
        print(f"Lookback hours: {args.lookback_hours}")
    
    print()
    
    try:
        if args.backfill:
            # Execute backfill operation
            await backfill_invoices_command(
                tenant=args.tenant,
                days_back=args.days_back,
                dry_run=args.dry_run
            )
        else:
            # Execute standard invoice generation
            await generate_invoices_command(
                tenant=args.tenant,
                lookback_hours=args.lookback_hours,
                dry_run=args.dry_run
            )
        
        print("\n✅ Invoice operation completed successfully")
        
    except KeyboardInterrupt:
        print("\n⏹️  Invoice operation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Invoice operation failed: {str(e)}")
        logger.error(f"Invoice operation failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
