#!/bin/bash
echo "Starting OS update..."
echo "Updating package lists..."
sudo apt update

echo ""
echo "Upgrading packages..."
sudo apt upgrade -y

echo ""
echo "Cleaning up..."
sudo apt autoremove -y
sudo apt autoclean

echo ""
echo "OS update completed successfully!"