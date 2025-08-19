# ==== EVENT STREAMING FLOW ==== #

"""
Prefect flow for controlled event streaming using Shopify Mock API.

This module provides comprehensive event streaming simulation capabilities
using the modern Shopify Mock API for realistic e-commerce order processing
and automated workflow orchestration for testing and development.
"""

import asyncio
import subprocess
import time
from typing import Dict, Any

import httpx
from prefect import flow, task, get_run_logger


# ==== EVENT STREAMING TASKS ==== #


@task
async def start_shopify_mock() -> Dict[str, Any]:
    """
    Start Shopify Mock API service.
    
    Initiates Docker-based Shopify Mock API with realistic
    order generation and webhook capabilities.
    
    Returns:
        Dict[str, Any]: Service startup status and configuration
    """
    logger = get_run_logger()
    logger.info("Starting Shopify Mock API service...")
    
    try:
        # Start the Shopify Mock API
        cmd = [
            "docker", "compose", "-f", "docker/docker-compose.yml", 
            "--profile", "demo", "up", "-d", "shopify-mock"
        ]
        
        logger.info(f"Starting Shopify Mock with command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd="/Users/sasha/IdeaProjects/octup/root")
        
        if result.returncode != 0:
            logger.error(f"Failed to start Shopify Mock: {result.stderr}")
            raise Exception(f"Shopify Mock start failed: {result.stderr}")
        
        # Wait for service to be ready
        logger.info("Waiting for Shopify Mock to be ready...")
        await asyncio.sleep(5)
        
        # Check health
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get("http://localhost:8090/health", timeout=10)
                if response.status_code == 200:
                    logger.info("Shopify Mock API started successfully")
                    health_data = response.json()
                    return {
                        "status": "started",
                        "service": "shopify-mock",
                        "health": health_data,
                        "endpoint": "http://localhost:8090"
                    }
                else:
                    raise Exception(f"Health check failed: {response.status_code}")
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                raise Exception(f"Shopify Mock health check failed: {e}")
        
    except Exception as e:
        logger.error(f"Shopify Mock startup failed: {str(e)}")
        raise


@task
async def generate_order_batch(batch_count: int = 1) -> Dict[str, Any]:
    """
    Generate batches of orders using Shopify Mock API.
    
    Args:
        batch_count (int): Number of batches to generate
        
    Returns:
        Dict[str, Any]: Generation results and statistics
    """
    logger = get_run_logger()
    logger.info(f"Generating {batch_count} order batches...")
    
    total_orders = 0
    total_problems = 0
    
    try:
        async with httpx.AsyncClient() as client:
            for i in range(batch_count):
                logger.info(f"Generating batch {i+1}/{batch_count}...")
                
                response = await client.post(
                    "http://localhost:8090/demo/generate-batch",
                    timeout=30
                )
                
                if response.status_code == 200:
                    batch_data = response.json()
                    batch_size = batch_data.get("batch_size", 0)
                    problems = batch_data.get("orders_with_problems", 0)
                    
                    total_orders += batch_size
                    total_problems += problems
                    
                    logger.info(f"Batch {i+1} generated: {batch_size} orders, {problems} with problems")
                    
                    # Small delay between batches
                    if i < batch_count - 1:
                        await asyncio.sleep(2)
                else:
                    logger.error(f"Batch generation failed: {response.status_code}")
                    raise Exception(f"Batch generation failed: {response.text}")
        
        return {
            "status": "completed",
            "batches_generated": batch_count,
            "total_orders": total_orders,
            "orders_with_problems": total_problems,
            "problem_rate": f"{(total_problems/total_orders*100):.1f}%" if total_orders > 0 else "0%"
        }
        
    except Exception as e:
        logger.error(f"Order batch generation failed: {str(e)}")
        raise


@task
async def stream_individual_orders(duration_minutes: int = 3, orders_per_minute: int = 10) -> Dict[str, Any]:
    """
    Stream individual orders for specified duration.
    
    Args:
        duration_minutes (int): How long to stream orders
        orders_per_minute (int): Rate of order generation
        
    Returns:
        Dict[str, Any]: Streaming statistics and completion status
    """
    logger = get_run_logger()
    logger.info(f"Streaming individual orders for {duration_minutes} minutes at {orders_per_minute} orders/min")
    
    try:
        duration_seconds = duration_minutes * 60
        interval_seconds = 60 / orders_per_minute
        
        start_time = time.time()
        orders_sent = 0
        
        async with httpx.AsyncClient() as client:
            while time.time() - start_time < duration_seconds:
                try:
                    response = await client.post(
                        "http://localhost:8090/demo/generate-order",
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        orders_sent += 1
                        order_data = response.json()
                        logger.info(f"Order {orders_sent} generated: {order_data.get('order_id', 'unknown')}")
                    else:
                        logger.warning(f"Order generation failed: {response.status_code}")
                    
                except Exception as e:
                    logger.warning(f"Order generation error: {e}")
                
                await asyncio.sleep(interval_seconds)
        
        actual_duration = time.time() - start_time
        
        return {
            "status": "completed",
            "duration_seconds": actual_duration,
            "orders_sent": orders_sent,
            "actual_rate": f"{orders_sent/(actual_duration/60):.1f} orders/min"
        }
        
    except Exception as e:
        logger.error(f"Order streaming failed: {str(e)}")
        raise


@task
async def get_demo_stats() -> Dict[str, Any]:
    """
    Get current demo statistics from Shopify Mock.
    
    Returns:
        Dict[str, Any]: Current demo statistics
    """
    logger = get_run_logger()
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8090/demo/stats", timeout=10)
            
            if response.status_code == 200:
                stats = response.json()
                logger.info(f"Demo stats: {stats['total_orders']} orders, {stats['problem_rate']} problem rate")
                return stats
            else:
                raise Exception(f"Stats request failed: {response.status_code}")
                
    except Exception as e:
        logger.error(f"Failed to get demo stats: {str(e)}")
        raise


@task
async def stop_shopify_mock() -> Dict[str, Any]:
    """
    Stop the Shopify Mock API service.
    
    Returns:
        Dict[str, Any]: Stop operation status and results
    """
    logger = get_run_logger()
    logger.info("Stopping Shopify Mock API service...")
    
    try:
        # Stop the Shopify Mock API
        cmd = [
            "docker", "compose", "-f", "docker/docker-compose.yml", 
            "stop", "shopify-mock"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd="/Users/sasha/IdeaProjects/octup/root")
        
        if result.returncode != 0:
            logger.warning(f"Shopify Mock stop warning: {result.stderr}")
        
        logger.info("Shopify Mock API stopped")
        
        return {"status": "stopped"}
        
    except Exception as e:
        logger.error(f"Failed to stop Shopify Mock: {str(e)}")
        # Don't raise - stopping is best effort
        return {"status": "stop_failed", "error": str(e)}


# ==== MAIN EVENT STREAMING FLOW ==== #


@flow(name="event-streaming", log_prints=True)
async def event_streaming_flow(
    mode: str = "batch",  # "batch" or "stream"
    duration_minutes: int = 3,
    batch_count: int = 2,
    orders_per_minute: int = 10,
    auto_stop: bool = True
) -> Dict[str, Any]:
    """
    Flow to simulate event streaming from Shopify using Mock API.
    
    This simulates realistic Shopify order processing with comprehensive
    flow orchestration and error handling.
    
    Args:
        mode (str): "batch" for batch generation, "stream" for individual orders
        duration_minutes (int): How long to stream (for stream mode)
        batch_count (int): Number of batches to generate (for batch mode)
        orders_per_minute (int): Orders per minute rate (for stream mode)
        auto_stop (bool): Whether to automatically stop service after completion
        
    Returns:
        Dict[str, Any]: Flow execution summary with detailed results
    """
    logger = get_run_logger()
    logger.info(f"Starting event streaming flow (mode: {mode})")
    
    try:
        # Start Shopify Mock service
        start_result = await start_shopify_mock()
        
        # Get initial stats
        initial_stats = await get_demo_stats()
        
        # Generate events based on mode
        if mode == "batch":
            logger.info(f"Running in batch mode: {batch_count} batches")
            generation_result = await generate_order_batch(batch_count)
        elif mode == "stream":
            logger.info(f"Running in stream mode: {duration_minutes}min at {orders_per_minute} orders/min")
            generation_result = await stream_individual_orders(duration_minutes, orders_per_minute)
        else:
            raise ValueError(f"Invalid mode: {mode}. Use 'batch' or 'stream'")
        
        # Get final stats
        final_stats = await get_demo_stats()
        
        # Auto-stop if requested
        stop_result = None
        if auto_stop:
            stop_result = await stop_shopify_mock()
        
        return {
            "status": "completed",
            "mode": mode,
            "service_start": start_result,
            "initial_stats": initial_stats,
            "generation": generation_result,
            "final_stats": final_stats,
            "stop": stop_result,
            "summary": f"Generated events in {mode} mode. Orders: {final_stats.get('total_orders', 0)}, Problems: {final_stats.get('problem_rate', '0%')}"
        }
        
    except Exception as e:
        logger.error(f"Event streaming flow failed: {str(e)}")
        
        # Try to stop service on failure
        try:
            await stop_shopify_mock()
        except:
            pass
            
        raise


# ==== COMMAND LINE INTERFACE ==== #


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Event streaming flow using Shopify Mock")
    parser.add_argument("--serve", action="store_true", help="Serve flow locally")
    parser.add_argument("--run", action="store_true", help="Run flow locally")
    parser.add_argument("--mode", choices=["batch", "stream"], default="batch", help="Generation mode")
    parser.add_argument("--duration", type=int, default=3, help="Duration in minutes (stream mode)")
    parser.add_argument("--batches", type=int, default=2, help="Number of batches (batch mode)")
    parser.add_argument("--rate", type=int, default=10, help="Orders per minute (stream mode)")
    
    args = parser.parse_args()
    
    if args.serve:
        print("Serving event streaming flow locally...")
        event_streaming_flow.serve(
            name="local-event-streaming",
            tags=["events", "streaming", "shopify", "local"],
            interval=None  # Manual triggering only
        )
        
    elif args.run:
        print(f"Running event streaming flow (mode: {args.mode})...")
        result = asyncio.run(event_streaming_flow(
            mode=args.mode,
            duration_minutes=args.duration,
            batch_count=args.batches,
            orders_per_minute=args.rate
        ))
        print(f"Flow completed: {result}")
        
    else:
        print("Usage: python flows/event_streaming.py [--run|--serve] [options]")
        print("  --run: Execute flow once locally")
        print("  --serve: Start flow server for manual triggering")
        print("  --mode [batch|stream]: Generation mode (default: batch)")
        print("  --duration N: Duration in minutes for stream mode (default: 3)")
        print("  --batches N: Number of batches for batch mode (default: 2)")
        print("  --rate N: Orders per minute for stream mode (default: 10)")
        print("")
        print("Examples:")
        print("  python flows/event_streaming.py --run --mode batch --batches 3")
        print("  python flows/event_streaming.py --run --mode stream --duration 5 --rate 15")
