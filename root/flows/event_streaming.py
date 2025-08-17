# ==== EVENT STREAMING FLOW ==== #

"""
Prefect flow for controlled event streaming (simulates Shopify/WMS).

This module provides comprehensive event streaming simulation capabilities
including controlled event generation, Docker-based simulator management,
and automated workflow orchestration for testing and development.
"""

import asyncio
import subprocess
import time
from typing import Dict, Any

from prefect import flow, task, get_run_logger


# ==== EVENT STREAMING TASKS ==== #


@task
async def start_event_stream(duration_minutes: int = 3, eps: int = 5) -> Dict[str, Any]:
    """
    Start event streaming for specified duration.
    
    Initiates Docker-based event simulator with configurable
    duration and event rate for comprehensive testing scenarios.
    
    Args:
        duration_minutes (int): How long to stream events in minutes
        eps (int): Events per second rate for simulation
        
    Returns:
        Dict[str, Any]: Streaming statistics and completion status
    """
    logger = get_run_logger()
    logger.info(f"Starting event stream for {duration_minutes} minutes at {eps} EPS")
    
    try:
        # Start the event simulator
        cmd = [
            "/opt/homebrew/bin/docker-compose", "-f", "docker/docker-compose.yml", 
            "--profile", "simulator", "up", "-d", "event-simulator"
        ]
        
        # Set environment variables for the simulator
        env = {
            "EPS": str(eps),
            "WORKERS": "2",
            "SIM_MODE": "push",
            "JITTER_MS": "100",
            "BURST_CHANCE": "0.1"
        }
        
        logger.info(f"Starting simulator with command: {' '.join(cmd)}")
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Failed to start simulator: {result.stderr}")
            raise Exception(f"Simulator start failed: {result.stderr}")
        
        logger.info("Event simulator started successfully")
        
        # Wait for the specified duration
        duration_seconds = duration_minutes * 60
        logger.info(f"Streaming events for {duration_seconds} seconds...")
        
        start_time = time.time()
        await asyncio.sleep(duration_seconds)
        end_time = time.time()
        
        actual_duration = end_time - start_time
        estimated_events = int(actual_duration * eps)
        
        logger.info(f"Event streaming completed after {actual_duration:.1f} seconds")
        
        return {
            "status": "completed",
            "duration_seconds": actual_duration,
            "estimated_events_sent": estimated_events,
            "eps": eps
        }
        
    except Exception as e:
        logger.error(f"Event streaming failed: {str(e)}")
        raise


@task
async def stop_event_stream() -> Dict[str, Any]:
    """
    Stop the event streaming.
    
    Gracefully terminates the event simulator with comprehensive
    error handling and status reporting for operational reliability.
    
    Returns:
        Dict[str, Any]: Stop operation status and results
    """
    logger = get_run_logger()
    logger.info("Stopping event stream...")
    
    try:
        # Stop the event simulator
        cmd = [
            "/opt/homebrew/bin/docker-compose", "-f", "docker/docker-compose.yml", 
            "stop", "event-simulator"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.warning(f"Simulator stop warning: {result.stderr}")
        
        logger.info("Event simulator stopped")
        
        return {"status": "stopped"}
        
    except Exception as e:
        logger.error(f"Failed to stop event stream: {str(e)}")
        # Don't raise - stopping is best effort
        return {"status": "stop_failed", "error": str(e)}


# ==== MAIN EVENT STREAMING FLOW ==== #


@flow(name="event-streaming", log_prints=True)
async def event_streaming_flow(
    duration_minutes: int = 3,
    eps: int = 5,
    auto_stop: bool = True
) -> Dict[str, Any]:
    """
    Flow to simulate event streaming from external systems.
    
    This simulates Shopify/WMS systems sending events to our API
    with comprehensive flow orchestration and error handling.
    
    Args:
        duration_minutes (int): How long to stream events
        eps (int): Events per second rate
        auto_stop (bool): Whether to automatically stop after duration
        
    Returns:
        Dict[str, Any]: Flow execution summary with detailed results
    """
    logger = get_run_logger()
    logger.info(f"Starting event streaming flow (duration: {duration_minutes}min, EPS: {eps})")
    
    try:
        # Start streaming
        stream_result = await start_event_stream(duration_minutes, eps)
        
        # Auto-stop if requested
        if auto_stop:
            stop_result = await stop_event_stream()
            
            return {
                "status": "completed",
                "streaming": stream_result,
                "stop": stop_result,
                "summary": f"Streamed ~{stream_result['estimated_events_sent']} events over {stream_result['duration_seconds']:.1f}s"
            }
        else:
            return {
                "status": "streaming_started",
                "streaming": stream_result,
                "note": "Stream not auto-stopped, manual stop required"
            }
            
    except Exception as e:
        logger.error(f"Event streaming flow failed: {str(e)}")
        
        # Try to stop simulator on failure
        try:
            await stop_event_stream()
        except:
            pass
            
        raise


# ==== COMMAND LINE INTERFACE ==== #


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Event streaming flow")
    parser.add_argument("--serve", action="store_true", help="Serve flow locally")
    parser.add_argument("--run", action="store_true", help="Run flow locally")
    parser.add_argument("--duration", type=int, default=3, help="Duration in minutes")
    parser.add_argument("--eps", type=int, default=5, help="Events per second")
    
    args = parser.parse_args()
    
    if args.serve:
        print("Serving event streaming flow locally...")
        event_streaming_flow.serve(
            name="local-event-streaming",
            tags=["events", "streaming", "local"],
            interval=None  # Manual triggering only
        )
        
    elif args.run:
        print(f"Running event streaming flow (duration: {args.duration}min, EPS: {args.eps})...")
        result = asyncio.run(event_streaming_flow(
            duration_minutes=args.duration,
            eps=args.eps
        ))
        print(f"Flow completed: {result}")
        
    else:
        print("Usage: python flows/event_streaming.py [--run|--serve] [options]")
        print("  --run: Execute flow once locally")
        print("  --serve: Start flow server for manual triggering")
        print("  --duration N: Duration in minutes (default: 3)")
        print("  --eps N: Events per second (default: 5)")
        print("")
        print("For deployment to local Prefect server, use: python deploy_prefect_local.py")
