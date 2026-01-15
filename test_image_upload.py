#!/usr/bin/env python3
"""Test script to verify image upload functionality with header.jpg"""

import base64
import requests
import json
from pathlib import Path

def encode_image_to_base64(image_path):
    """Convert image file to base64 data URI"""
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    # Determine mime type
    ext = Path(image_path).suffix.lower()
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }
    mime_type = mime_types.get(ext, 'image/jpeg')
    
    # Encode to base64 and create data URI
    b64_data = base64.b64encode(image_data).decode('utf-8')
    return f"data:{mime_type};base64,{b64_data}"

def test_image_upload():
    """Test uploading header.jpg to the API"""
    base_url = "http://localhost:8001"
    
    print("🧪 Testing Image Upload Functionality")
    print("=" * 50)
    
    # Step 1: Create conversation
    print("\n1. Creating new conversation...")
    response = requests.post(f"{base_url}/api/conversations")
    if response.status_code != 200:
        print(f"❌ Failed to create conversation: {response.status_code}")
        return
    
    conversation = response.json()
    conv_id = conversation['id']
    print(f"✅ Created conversation: {conv_id}")
    
    # Step 2: Encode header.jpg
    print("\n2. Encoding header.jpg to base64...")
    image_path = Path(__file__).parent / "header.jpg"
    
    if not image_path.exists():
        print(f"❌ header.jpg not found at {image_path}")
        return
    
    image_base64 = encode_image_to_base64(image_path)
    print(f"✅ Encoded image ({len(image_base64)} characters)")
    
    # Step 3: Send message with image
    print("\n3. Sending message with image...")
    print("   Query: What do you see in this image?")
    
    payload = {
        "content": "What do you see in this image? Describe it in detail.",
        "images": [image_base64]
    }
    
    response = requests.post(
        f"{base_url}/api/conversations/{conv_id}/message",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to send message: {response.status_code}")
        print(f"   Response: {response.text}")
        return
    
    result = response.json()
    print(f"✅ Message sent successfully!")
    
    # Step 4: Display results
    print("\n" + "=" * 50)
    print("📊 RESULTS")
    print("=" * 50)
    
    print("\n🎯 Stage 1 - Individual Responses:")
    for i, resp in enumerate(result.get('stage1', []), 1):
        model = resp['model']
        response_text = resp['response'][:200] + "..." if len(resp['response']) > 200 else resp['response']
        print(f"\n  Model {i}: {model}")
        print(f"  Response: {response_text}")
    
    print("\n🏆 Stage 2 - Aggregate Rankings:")
    if result.get('metadata', {}).get('aggregate_rankings'):
        for ranking in result['metadata']['aggregate_rankings']:
            print(f"  {ranking['model']}: avg rank {ranking['average_rank']}")
    
    print("\n👑 Stage 3 - Final Answer:")
    stage3 = result.get('stage3', {})
    final_text = stage3.get('response', '')[:300] + "..." if len(stage3.get('response', '')) > 300 else stage3.get('response', '')
    print(f"  {final_text}")
    
    print("\n" + "=" * 50)
    print("✅ TEST COMPLETED SUCCESSFULLY!")
    print("=" * 50)
    print(f"\n💡 View full conversation in UI: http://localhost:5173")

if __name__ == "__main__":
    test_image_upload()
