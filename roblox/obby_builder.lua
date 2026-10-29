--[[
	OBBY-BUILDER – baut ein komplettes Obby in Roblox Studio

	So geht's:
	  1. Roblox Studio öffnen, neues "Baseplate"-Spiel (oder dein Spiel) öffnen
	  2. Oben: Ansicht (View) → "Befehlsleiste" / "Command Bar" einschalten
	  3. DIESEN GANZEN TEXT in die Befehlsleiste kopieren und Enter drücken
	  4. Oben auf "Spielen" (Play) drücken und testen

	Was gebaut wird:
	  - 12 Stages mit 6 Hindernis-Arten (Sprünge, Lava, Treppe, verschwindende
	    Plattformen, Drehbalken, Kletter-Gerüst)
	  - Checkpoints (man spawnt nach dem Tod am letzten Checkpoint)
	  - Lava unter dem ganzen Parcours
	  - Bestenliste (Stage) und Timer oben im Bild
	  - Ziel mit "Geschafft!"-Anzeige

	Nochmal einfügen = altes Obby wird gelöscht und neu gebaut.
	Rückgängig: Strg+Z
]]

local STAGES = 12     -- Anzahl Stages (Vielfaches von 6 sieht am besten aus)
local BASE_Y = 20     -- Höhe des Parcours über dem Boden

local ChangeHistoryService = game:GetService("ChangeHistoryService")
local ServerScriptService = game:GetService("ServerScriptService")
local StarterGui = game:GetService("StarterGui")

-- Alte Version entfernen
for _, parentAndName in { { workspace, "Obby" }, { ServerScriptService, "ObbyServer" }, { StarterGui, "ObbyGui" } } do
	local old = parentAndName[1]:FindFirstChild(parentAndName[2])
	if old then old:Destroy() end
end

local obby = Instance.new("Folder")
obby.Name = "Obby"
obby:SetAttribute("Stages", STAGES)

local checkpoints = Instance.new("Folder")
checkpoints.Name = "Checkpoints"
checkpoints.Parent = obby

local COLORS = {
	platform = Color3.fromRGB(230, 230, 235),
	jump = Color3.fromRGB(255, 170, 60),
	kill = Color3.fromRGB(255, 40, 40),
	blink = Color3.fromRGB(80, 160, 255),
	checkpoint = Color3.fromRGB(60, 220, 100),
	finish = Color3.fromRGB(255, 205, 50),
}

local function makePart(name, size, position, color, parent)
	local p = Instance.new("Part")
	p.Name = name
	p.Anchored = true
	p.Size = size
	p.Position = position
	p.Color = color
	p.Material = Enum.Material.SmoothPlastic
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent or obby
	return p
end

local function makeKill(size, position)
	local p = makePart("Lava", size, position, COLORS.kill)
	p.Material = Enum.Material.Neon
	p:SetAttribute("Kill", true)
	return p
end

-- ---------- Hindernisse ----------
-- Jede Funktion bekommt die Vorderkante z (Richtung -Z) und Höhe y
-- und gibt die neue Vorderkante und Höhe zurück.

local obstacles = {}

-- 1) Sprünge im Zickzack
obstacles[1] = function(z, y)
	for i = 1, 4 do
		local x = (i % 2 == 0) and 3 or -3
		z -= 5
		makePart("Jump", Vector3.new(4, 1, 4), Vector3.new(x, y, z - 2), COLORS.jump)
		z -= 4
	end
	return z, y
end

-- 2) Langer Weg mit Lava-Streifen zum Drüberspringen
obstacles[2] = function(z, y)
	z -= 3
	local length = 30
	makePart("LavaRun", Vector3.new(6, 1, length), Vector3.new(0, y, z - length / 2), COLORS.platform)
	for d = 6, length - 5, 6 do
		makeKill(Vector3.new(6, 0.4, 1.5), Vector3.new(0, y + 0.7, z - d))
	end
	return z - length, y
end

-- 3) Treppe nach oben
obstacles[3] = function(z, y)
	for _ = 1, 5 do
		z -= 4
		y += 3
		makePart("Stair", Vector3.new(5, 1, 5), Vector3.new(0, y, z - 2.5), COLORS.jump)
		z -= 5
	end
	return z, y
end

-- 4) Verschwindende Plattformen
obstacles[4] = function(z, y)
	for i = 1, 4 do
		z -= 4
		local p = makePart("Blink", Vector3.new(5, 1, 5), Vector3.new(0, y, z - 2.5), COLORS.blink)
		p:SetAttribute("Blink", i % 2) -- abwechselnd sichtbar
		z -= 5
	end
	return z, y
end

-- 5) Plattform mit Drehbalken
obstacles[5] = function(z, y)
	z -= 4
	local center = Vector3.new(0, y, z - 8)
	makePart("SpinnerFloor", Vector3.new(16, 1, 16), center, COLORS.platform)
	local bar = makeKill(Vector3.new(15, 1, 1), center + Vector3.new(0, 1.2, 0))
	bar.Name = "Spinner"
	bar:SetAttribute("Spin", 2) -- Drehgeschwindigkeit
	return z - 16, y
end

-- 6) Kletter-Gerüst nach oben
obstacles[6] = function(z, y)
	z -= 3
	makePart("TrussBase", Vector3.new(6, 1, 6), Vector3.new(0, y, z - 3), COLORS.platform)
	z -= 6
	local truss = Instance.new("TrussPart")
	truss.Name = "Truss"
	truss.Anchored = true
	truss.Size = Vector3.new(2, 16, 2)
	truss.Position = Vector3.new(0, y + 8.5, z - 1)
	truss.Parent = obby
	z -= 2
	y += 16
	makePart("TrussTop", Vector3.new(6, 1, 6), Vector3.new(0, y, z - 3), COLORS.platform)
	return z - 6, y
end

-- ---------- Parcours bauen ----------
local start = Instance.new("SpawnLocation")
start.Name = "Checkpoint0"
start.Anchored = true
start.Size = Vector3.new(12, 1, 12)
start.Position = Vector3.new(0, BASE_Y, 0)
start.Color = COLORS.checkpoint
start.Material = Enum.Material.SmoothPlastic
start.Neutral = true
start.Duration = 0
start:SetAttribute("Stage", 0)
start.Parent = checkpoints

local z, y = -6, BASE_Y
for stage = 1, STAGES do
	z, y = obstacles[(stage - 1) % #obstacles + 1](z, y)

	local isLast = stage == STAGES
	z -= 4
	local cp = makePart(
		isLast and "Finish" or ("Checkpoint" .. stage),
		Vector3.new(isLast and 14 or 10, 1, isLast and 14 or 10),
		Vector3.new(0, y, z - (isLast and 7 or 5)),
		isLast and COLORS.finish or COLORS.checkpoint,
		isLast and obby or checkpoints
	)
	cp.Material = Enum.Material.Neon
	cp:SetAttribute("Stage", stage)
	z -= isLast and 14 or 10
end

-- Lava-Boden unter dem ganzen Parcours
local length = -z + 40
makeKill(Vector3.new(80, 1, length), Vector3.new(0, BASE_Y - 12, z / 2))

obby.Parent = workspace

-- ---------- Server-Skript ----------
local server = Instance.new("Script")
server.Name = "ObbyServer"
server.Source = [==[
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local obby = workspace:WaitForChild("Obby")
local checkpoints = obby:WaitForChild("Checkpoints")
local finish = obby:WaitForChild("Finish")
local STAGES = obby:GetAttribute("Stages")

local function playerFromHit(hit)
	local character = hit:FindFirstAncestorOfClass("Model")
	if not character then return nil end
	local humanoid = character:FindFirstChildOfClass("Humanoid")
	if not humanoid or humanoid.Health <= 0 then return nil end
	return Players:GetPlayerFromCharacter(character), humanoid
end

-- Spieler: Stage-Anzeige, Timer, Spawn am letzten Checkpoint
Players.PlayerAdded:Connect(function(player)
	local leaderstats = Instance.new("Folder")
	leaderstats.Name = "leaderstats"
	local stage = Instance.new("IntValue")
	stage.Name = "Stage"
	stage.Parent = leaderstats
	leaderstats.Parent = player

	player:SetAttribute("StartTime", workspace:GetServerTimeNow())

	-- Immer zum letzten Checkpoint (auch wenn es noch andere SpawnLocations gibt)
	player.CharacterAdded:Connect(function(character)
		local cp = checkpoints:FindFirstChild("Checkpoint" .. stage.Value)
		if cp then
			character:WaitForChild("HumanoidRootPart")
			task.wait()
			character:PivotTo(cp.CFrame + Vector3.new(0, 4, 0))
		end
	end)
end)

-- Checkpoints (nur der nächste zählt, kein Überspringen)
for _, cp in checkpoints:GetChildren() do
	cp.Touched:Connect(function(hit)
		local player = playerFromHit(hit)
		if not player then return end
		local stage = player.leaderstats.Stage
		if cp:GetAttribute("Stage") == stage.Value + 1 then
			stage.Value += 1
		end
	end)
end

-- Ziel
finish.Touched:Connect(function(hit)
	local player = playerFromHit(hit)
	if not player or player:GetAttribute("FinishTime") then return end
	local stage = player.leaderstats.Stage
	if stage.Value == STAGES - 1 then
		stage.Value = STAGES
		player:SetAttribute("FinishTime", workspace:GetServerTimeNow())
	end
end)

-- Lava, verschwindende Plattformen, Drehbalken
local blinking, spinning = {}, {}
for _, part in obby:GetDescendants() do
	if not part:IsA("BasePart") then continue end
	if part:GetAttribute("Kill") then
		part.Touched:Connect(function(hit)
			local _, humanoid = playerFromHit(hit)
			if humanoid then humanoid.Health = 0 end
		end)
	end
	if part:GetAttribute("Blink") ~= nil then table.insert(blinking, part) end
	if part:GetAttribute("Spin") then
		table.insert(spinning, { part = part, center = part.Position, speed = part:GetAttribute("Spin") })
	end
end

task.spawn(function()
	local phase = 0
	while true do
		for _, part in blinking do
			local visible = part:GetAttribute("Blink") == phase
			part.Transparency = visible and 0 or 0.8
			part.CanCollide = visible
		end
		phase = 1 - phase
		task.wait(2.5)
	end
end)

RunService.Heartbeat:Connect(function()
	local t = os.clock()
	for _, s in spinning do
		s.part.CFrame = CFrame.new(s.center) * CFrame.Angles(0, t * s.speed, 0)
	end
end)
]==]
server.Parent = ServerScriptService

-- ---------- Anzeige (Stage + Timer) ----------
local gui = Instance.new("ScreenGui")
gui.Name = "ObbyGui"
gui.ResetOnSpawn = false

local label = Instance.new("TextLabel")
label.Name = "Info"
label.Size = UDim2.new(0, 380, 0, 44)
label.Position = UDim2.new(0.5, -190, 0, 10)
label.BackgroundColor3 = Color3.new(0, 0, 0)
label.BackgroundTransparency = 0.35
label.TextColor3 = Color3.new(1, 1, 1)
label.Font = Enum.Font.GothamBold
label.TextScaled = true
label.Text = ""
label.Parent = gui
Instance.new("UICorner").Parent = label

local client = Instance.new("LocalScript")
client.Name = "ObbyHud"
client.Source = [==[
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local player = Players.LocalPlayer
local label = script.Parent:WaitForChild("Info")
local total = workspace:WaitForChild("Obby"):GetAttribute("Stages")
local stage = player:WaitForChild("leaderstats"):WaitForChild("Stage")

local function fmt(t)
	return string.format("%d:%04.1f", math.floor(t / 60), t % 60)
end

RunService.RenderStepped:Connect(function()
	local start = player:GetAttribute("StartTime")
	if not start then return end
	local finish = player:GetAttribute("FinishTime")
	if finish then
		label.Text = "🏆 Geschafft! Zeit: " .. fmt(finish - start)
	else
		label.Text = string.format("Stage %d/%d   ⏱ %s", stage.Value, total, fmt(workspace:GetServerTimeNow() - start))
	end
end)
]==]
client.Parent = gui
gui.Parent = StarterGui

pcall(function() ChangeHistoryService:SetWaypoint("Obby gebaut") end)
print("✅ Obby mit " .. STAGES .. " Stages gebaut! Drück auf Spielen zum Testen.")
