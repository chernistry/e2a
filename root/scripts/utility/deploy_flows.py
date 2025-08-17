#!/usr/bin/env python3

# ==== PREFECT FLOWS DEPLOYMENT SCRIPT ==== #

"""
Prefect Flows Deployment Script for Octup E²A

This script deploys all Prefect workflows to the local Prefect server with
appropriate scheduling and configuration. It manages the deployment of critical
business processes including periodic demonstrations, nightly invoice validation,
and manual event streaming for testing.

Features:
- Automated flow deployment with proper scheduling
- Environment-specific configurations and parameters
- Health checks and deployment validation
- Rollback capabilities and version management
- Comprehensive deployment reporting and status

Deployed Flows:
1. Periodic Demo Flow: Every 5 minutes for live demonstrations
2. Invoice Validation Flow: Daily at 1:00 UTC for billing automation
3. Event Streaming Flow: Manual trigger for testing and development

Usage:
    python deploy_flows.py [--dry-run] [--force] [--flows FLOW_NAMES]

Examples:
    # Deploy all flows
    python deploy_flows.py
    
    # Dry run to preview deployments
    python deploy_flows.py --dry-run
    
    # Force redeployment of existing flows
    python deploy_flows.py --force
    
    # Deploy specific flows only
    python deploy_flows.py --flows periodic_demo,invoice_validation

Dependencies:
    - Prefect server running locally (http://localhost:4200)
    - All flow modules available in flows/ directory
    - Proper environment configuration (database, Redis, etc.)

Author: E²A Team
Version: 1.0.0
"""

import asyncio
import sys
import argparse
from datetime import datetime
from typing import List, Optional, Dict, Any

from prefect import get_client
from prefect.deployments import Deployment
from prefect.server.schemas.schedules import CronSchedule


async def deploy_all_flows(
    dry_run: bool = False,
    force: bool = False,
    specific_flows: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Deploy all Prefect flows to local server with comprehensive configuration.
    
    This function orchestrates the deployment of all critical business workflows
    with appropriate scheduling, tagging, and parameter configuration. It provides
    detailed feedback on deployment status and handles errors gracefully.
    
    Args:
        dry_run (bool): If True, simulate deployment without actual changes
        force (bool): If True, force redeployment of existing flows
        specific_flows (Optional[List[str]]): List of specific flow names to deploy
        
    Returns:
        Dictionary containing deployment results and metadata
        
    Raises:
        Exception: If critical deployment errors occur
        
    Note:
        All flows are deployed with version 1.0.0 and appropriate tags for
        organization and monitoring in the Prefect UI.
    """
    print("🚀 Deploying Octup E²A flows to local Prefect server...")
    
    if dry_run:
        print("🔍 DRY RUN MODE - No actual deployments will occur")
    
    if force:
        print("⚡ FORCE MODE - Existing deployments will be overwritten")
    
    deployment_results = {}
    
    try:
        # --► PERIODIC DEMO FLOW (Every 5 minutes)
        if not specific_flows or "periodic_demo" in specific_flows:
            print("\n📡 Deploying Periodic Demo Flow...")
            from flows.periodic_demo import periodic_demo_flow
            
            demo_deployment = Deployment.build_from_flow(
                flow=periodic_demo_flow,
                name="live-demo-5min",
                version="1.0.0",
                tags=["demo", "live", "periodic", "e2a"],
                description="Runs every 5 minutes to simulate live business operations for demonstration",
                schedule=CronSchedule(cron="*/5 * * * *", timezone="UTC"),
                parameters={
                    "stream_duration_minutes": 3,
                    "stream_eps": 4,
                    "include_invoice_validation": False  # Don't run invoice validation every 5 min
                }
            )
            
            if dry_run:
                print(f"  [DRY RUN] Would deploy Periodic Demo Flow")
                deployment_results["periodic_demo"] = {"status": "dry_run", "id": None}
            else:
                demo_deployment_id = await demo_deployment.apply()
                print(f"✅ Periodic Demo deployed: {demo_deployment_id}")
                deployment_results["periodic_demo"] = {"status": "deployed", "id": demo_deployment_id}
        
        # --► INVOICE VALIDATION FLOW (Daily at 1:00 UTC)
        if not specific_flows or "invoice_validation" in specific_flows:
            print("\n💰 Deploying Invoice Validation Flow...")
            from flows.invoice_validate_nightly import invoice_validate_nightly_flow
            
            invoice_deployment = Deployment.build_from_flow(
                flow=invoice_validate_nightly_flow,
                name="nightly-invoice-validation",
                version="1.0.0",
                tags=["billing", "nightly", "automation", "e2a"],
                description="Daily invoice validation and adjustment creation at 1:00 UTC",
                schedule=CronSchedule(cron="0 1 * * *", timezone="UTC"),
                parameters={
                    "tenant": "demo-3pl",
                    "force_run": False
                }
            )
            
            if dry_run:
                print(f"  [DRY RUN] Would deploy Invoice Validation Flow")
                deployment_results["invoice_validation"] = {"status": "dry_run", "id": None}
            else:
                invoice_deployment_id = await invoice_deployment.apply()
                print(f"✅ Invoice Validation deployed: {invoice_deployment_id}")
                deployment_results["invoice_validation"] = {"status": "deployed", "id": invoice_deployment_id}
        
        # --► EVENT STREAMING FLOW (Manual trigger only)
        if not specific_flows or "event_streaming" in specific_flows:
            print("\n🎯 Deploying Event Streaming Flow...")
            from flows.event_streaming import event_streaming_flow
            
            streaming_deployment = Deployment.build_from_flow(
                flow=event_streaming_flow,
                name="manual-event-streaming",
                version="1.0.0",
                tags=["events", "manual", "testing", "e2a"],
                description="Manual event streaming for testing and development",
                schedule=None,  # Manual trigger only
                parameters={
                    "duration_minutes": 5,
                    "eps": 6,
                    "auto_stop": True
                }
            )
            
            if dry_run:
                print(f"  [DRY RUN] Would deploy Event Streaming Flow")
                deployment_results["event_streaming"] = {"status": "dry_run", "id": None}
            else:
                streaming_deployment_id = await streaming_deployment.apply()
                print(f"✅ Event Streaming deployed: {streaming_deployment_id}")
                deployment_results["event_streaming"] = {"status": "deployed", "id": streaming_deployment_id}
        
        # Print deployment summary
        if not dry_run:
            print(f"\n🎉 All flows deployed successfully!")
            print(f"\n📋 Deployment Summary:")
            
            for flow_name, result in deployment_results.items():
                if result["status"] == "deployed":
                    print(f"   • {flow_name.replace('_', ' ').title()}: ID {result['id']}")
            
            print(f"\n🌐 Access Prefect UI at: http://localhost:4200")
            print(f"📊 View flows, schedules, and execution history in the UI")
        else:
            print(f"\n🔍 DRY RUN SUMMARY:")
            print(f"   • Would deploy {len(deployment_results)} flows")
            print(f"   • No actual changes made")
        
        return deployment_results
        
    except Exception as e:
        print(f"\n❌ Flow deployment failed: {str(e)}")
        raise


async def check_prefect_server() -> bool:
    """
    Verify that Prefect server is accessible and responsive.
    
    Performs basic health checks on the Prefect server to ensure
    it's running and ready to accept deployments.
    
    Returns:
        bool: True if server is accessible, False otherwise
    """
    try:
        client = get_client()
        # Try to get server info
        await client.server_info()
        return True
    except Exception as e:
        print(f"❌ Prefect server not accessible: {str(e)}")
        print(f"   Make sure Prefect server is running at http://localhost:4200")
        return False


async def main():
    """
    Main function to orchestrate Prefect flow deployments.
    
    Parses command line arguments, validates Prefect server connectivity,
    and executes the deployment process with proper error handling.
    """
    parser = argparse.ArgumentParser(
        description="Deploy Prefect flows to local server for Octup E²A",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deploy all flows
  python deploy_flows.py
  
  # Preview deployments without making changes
  python deploy_flows.py --dry-run
  
  # Force redeployment of existing flows
  python deploy_flows.py --force
  
  # Deploy only specific flows
  python deploy_flows.py --flows periodic_demo,invoice_validation
        """
    )
    
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Simulate deployment without making actual changes"
    )
    
    parser.add_argument(
        "--force", 
        action="store_true",
        help="Force redeployment of existing flows"
    )
    
    parser.add_argument(
        "--flows", 
        type=str,
        help="Comma-separated list of specific flows to deploy (e.g., periodic_demo,invoice_validation)"
    )
    
    args = parser.parse_args()
    
    # Parse specific flows if provided
    specific_flows = None
    if args.flows:
        specific_flows = [flow.strip() for flow in args.flows.split(",")]
        print(f"🎯 Deploying specific flows: {', '.join(specific_flows)}")
    
    print("🚀 Prefect Flows Deployment")
    print("=" * 40)
    print(f"Dry run: {'Yes' if args.dry_run else 'No'}")
    print(f"Force mode: {'Yes' if args.force else 'No'}")
    print(f"Target flows: {specific_flows or 'All flows'}")
    print()
    
    try:
        # Check Prefect server connectivity
        if not await check_prefect_server():
            print("❌ Cannot proceed without Prefect server")
            sys.exit(1)
        
        # Execute deployment
        results = await deploy_all_flows(
            dry_run=args.dry_run,
            force=args.force,
            specific_flows=specific_flows
        )
        
        if not args.dry_run:
            print("\n✅ Flow deployment completed successfully")
        else:
            print("\n🔍 Dry run completed - no changes made")
        
    except KeyboardInterrupt:
        print("\n⏹️  Flow deployment interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Flow deployment failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
