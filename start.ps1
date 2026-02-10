#Windows startup script
Write-Host "`n=== Charles AI Assistant — Starting ===" -ForegroundColor Cyan

# Start containers
Write-Host "[*] Pulling latest images and starting containers..." -ForegroundColor Green
docker compose up -d

# Show status
Write-Host "`n[*] Container status:" -ForegroundColor Green
docker compose ps

Write-Host "`n=== Charles is running at http://localhost:3000 ===" -ForegroundColor Cyan
Write-Host "    First visit: create an admin account (first user = admin)." -ForegroundColor White
Write-Host "    Then go to Settings -> Connections to add your API key." -ForegroundColor White
Write-Host "    To stop:  docker compose down" -ForegroundColor White
Write-Host "    Logs:     docker compose logs -f`n" -ForegroundColor White
