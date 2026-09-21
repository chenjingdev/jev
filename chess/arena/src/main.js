import './styles.css'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js'
import { Chess } from 'chess.js'

const ASSET_ROOT = '/assets/chess/'
const PIECE_FILES = { p: 'pawn.glb', r: 'rook.glb', n: 'knight.glb', b: 'bishop.glb', q: 'queen.glb', k: 'king.glb' }
const SQUARE = 0.05
const VIEW_HALF_SIZE = .244
const BOARD_TOP = 0.0205
const NORMAL_MOVE_MS = 220
const NORMAL_PAUSE_MS = 120
const INTERVENTION_PREVIEW_MS = 900
const INTERVENTION_MOVE_MS = 700
const INTERVENTION_PAUSE_MS = 1100
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches

const els = Object.fromEntries([
  'scene', 'loading', 'black-name', 'white-name', 'jev-panel', 'jev-state', 'fx-button',
  'prev-button', 'play-button', 'next-button', 'timeline', 'timeline-time', 'game-select',
  'camera-button', 'fullscreen-button', 'export-button', 'export-status', 'share-frame', 'visual-badge',
  'route-comparison', 'route-base-move', 'route-selected-move'
].map(id => [id, document.getElementById(id)]))

let renderer, scene, camera, controls, boardRoot, pieceRoot, effectRoot
let templates = {}
let pieceObjects = new Map()
let matchData = null
let game = null
let gameIndex = 0
let ply = 0
let replay = new Chess()
let playing = false
let playTimer = null
let fxPreview = false
let animation = null
let cameraPreset = 0
let ready = false
let exporting = false
let resizeObserver

init().catch(error => {
  console.error(error)
  els.loading.querySelector('p').textContent = `LOAD FAILED · ${error.message}`
})

async function init() {
  initScene()
  bindControls()
  setReady(false)
  const [data] = await Promise.all([loadMatch(), loadAssets()])
  matchData = data
  populateGameSelect()
  const params = new URLSearchParams(location.search)
  const requestedGame = Number(params.get('game') || 0)
  selectGame(Number.isInteger(requestedGame) && requestedGame >= 0 && requestedGame < matchData.games.length ? requestedGame : 0)
  const requestedPly = Number(params.get('ply') || 0)
  if (Number.isInteger(requestedPly) && requestedPly > 0) seek(Math.min(requestedPly, game.moves.length))
  els.loading.classList.add('hidden')
  setReady(true)
  animate(performance.now())
}

function initScene() {
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0xe6e9dd)
  camera = new THREE.OrthographicCamera(-VIEW_HALF_SIZE, VIEW_HALF_SIZE, VIEW_HALF_SIZE, -VIEW_HALF_SIZE, .01, 10)
  camera.position.set(0, .9, .5)
  camera.lookAt(0, .014, 0)
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = .95
  renderer.outputColorSpace = THREE.SRGBColorSpace
  els.scene.appendChild(renderer.domElement)
  controls = new OrbitControls(camera, renderer.domElement)
  controls.target.set(0, .014, 0)
  controls.enableDamping = true
  controls.dampingFactor = .09
  controls.minZoom = .75
  controls.maxZoom = 1.4
  controls.minPolarAngle = .02
  controls.maxPolarAngle = .9
  controls.enablePan = false
  boardRoot = new THREE.Group()
  pieceRoot = new THREE.Group()
  effectRoot = new THREE.Group()
  scene.add(boardRoot, pieceRoot, effectRoot)
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(5, 5), new THREE.MeshStandardMaterial({ color: 0xe6e9dd, roughness: 1 }))
  floor.rotation.x = -Math.PI / 2
  floor.position.y = -.01
  floor.receiveShadow = true
  scene.add(floor)
  scene.add(new THREE.HemisphereLight(0xffffff, 0xa6b894, 1.1))
  const key = new THREE.DirectionalLight(0xfff9e9, 1.9)
  key.position.set(-.5, 1, .35)
  key.castShadow = true
  key.shadow.mapSize.set(2048, 2048)
  key.shadow.camera.left = key.shadow.camera.bottom = -.4
  key.shadow.camera.right = key.shadow.camera.top = .4
  key.shadow.camera.near = .1
  key.shadow.camera.far = 3
  key.shadow.bias = -.00015
  key.shadow.normalBias = .0006
  key.shadow.radius = 3
  scene.add(key)
  scene.environmentIntensity = .5
  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(els.scene)
  resize()
}

async function loadAssets() {
  const loader = new GLTFLoader()
  const load = url => new Promise((resolve, reject) => loader.load(url, resolve, undefined, reject))
  const textureLoader = new THREE.TextureLoader()
  const loadTexture = url => new Promise((resolve, reject) => textureLoader.load(url, resolve, undefined, reject))
  const [entries, environment, walnutColor, walnutNormal, walnutRoughness] = await Promise.all([
    Promise.all([
    ...Object.entries(PIECE_FILES).map(async ([type, file]) => [type, (await load(ASSET_ROOT + file)).scene]),
    (async () => ['board', (await load(ASSET_ROOT + 'board.glb')).scene])()
    ]),
    new HDRLoader().loadAsync('/assets/environment/studio_small_09_1k.hdr'),
    loadTexture('/assets/materials/walnut_diff_1k.jpg'),
    loadTexture('/assets/materials/walnut_nor_gl_1k.jpg'),
    loadTexture('/assets/materials/walnut_rough_1k.jpg')
  ])
  const pmrem = new THREE.PMREMGenerator(renderer)
  const previousEnvironment = scene.environment
  scene.environment = pmrem.fromEquirectangular(environment).texture
  previousEnvironment?.dispose()
  environment.dispose()
  pmrem.dispose()
  walnutColor.colorSpace = THREE.SRGBColorSpace
  for (const texture of [walnutColor, walnutNormal, walnutRoughness]) {
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping
    texture.repeat.set(2.4, 2.4)
    texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy())
  }
  for (const [name, object] of entries) {
    object.traverse(child => {
      if (!child.isMesh) return
      child.castShadow = name !== 'board'
      child.receiveShadow = true
      if (child.material) child.material = child.material.clone()
      if (child.material?.name === 'walnut') {
        child.material.map = walnutColor
        child.material.normalMap = walnutNormal
        child.material.roughnessMap = walnutRoughness
        child.material.color.set(0xb2aa8c)
        child.material.normalScale.set(.14, .14)
        child.material.roughness = .9
        child.material.needsUpdate = true
      }
      if (name === 'board') {
        if (child.material.name === 'ivory') child.material.color.set(0xd6d3bf)
        if (child.material.name === 'ebony') child.material.color.set(0x64806c)
        if (child.material.name === 'gold') child.material.color.set(0x8b8d64)
        child.material.metalness = 0
        child.material.roughness = .84
      }
    })
    if (name === 'board') {
      boardRoot.add(object)

    } else {
      templates[name] = object
    }
  }
  addBoardCoordinates()
}

function addBoardCoordinates() {
  for (let i = 0; i < 8; i++) {
    for (const [label, x, z] of [[String.fromCharCode(97 + i), (i - 3.5) * SQUARE, .216], [String(8 - i), -.216, (i - 3.5) * SQUARE]]) {
      const canvas = document.createElement('canvas')
      canvas.width = canvas.height = 64
      const ctx = canvas.getContext('2d')
      ctx.font = '500 38px sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = '#f4f1e4'
      ctx.fillText(label, 32, 32)
      const map = new THREE.CanvasTexture(canvas)
      const marker = new THREE.Mesh(new THREE.PlaneGeometry(.010, .010), new THREE.MeshBasicMaterial({ map, transparent: true, depthWrite: false }))
      marker.rotation.x = -Math.PI / 2
      marker.position.set(x, .020, z)
      boardRoot.add(marker)
    }
  }
}

async function loadMatch() {
  const name = new URLSearchParams(location.search).get('match')
  if (name) {
    const response = await fetch(`/api/match?name=${encodeURIComponent(name)}`, { cache: 'no-store' })
    if (!response.ok) throw new Error('Requested match unavailable')
    const data = await response.json()
    if (!data.games?.length) throw new Error('Requested match has no moves yet')
    return data
  }
  const urls = ['/api/match', '/data/sunfish-smoke.json']
  for (const url of urls) {
    try {
      const response = await fetch(url, { cache: 'no-store' })
      if (response.ok) return await response.json()
    } catch (_) { /* use the packaged replay fallback */ }
  }
  throw new Error('match data unavailable')
}

function populateGameSelect() {
  els['game-select'].innerHTML = matchData.games.map((g, i) =>
    `<option value="${i}">대국 ${String(g.game).padStart(2, '0')} · ${escapeHtml(g.white)}</option>`
  ).join('')
}

function selectGame(index) {
  stopPlayback()
  animation = null
  gameIndex = Number(index)
  game = matchData.games[gameIndex]
  ply = 0
  els['game-select'].value = String(gameIndex)
  els.timeline.max = String(game.moves.length)
  els['white-name'].textContent = game.white
  els['black-name'].textContent = game.black
  seekDirect(0)
}

function renderPieces(chess) {
  pieceRoot.traverse(object => { if (object.isMesh) object.material.dispose() })
  pieceRoot.clear()
  pieceObjects.clear()
  for (const row of chess.board()) {
    for (const item of row) {
      if (!item) continue
      const piece = createPiece(item.type, item.color)
      const pos = squarePosition(item.square)
      piece.position.set(pos.x, BOARD_TOP, pos.z)
      piece.userData.square = item.square
      pieceRoot.add(piece)
      pieceObjects.set(item.square, piece)
    }
  }
}

function createPiece(type, color) {
  const root = templates[type].clone(true)
  root.traverse(child => {
    if (!child.isMesh) return
    const source = child.material
    child.material = source.clone()
    if (source.name === 'ivory') {
      child.material.color.set(color === 'w' ? 0xe7d9b7 : 0x183d2e)
      child.material.roughness = color === 'w' ? .38 : .40
      child.material.metalness = 0
      child.material.clearcoat = .35
      child.material.clearcoatRoughness = .33
    } else if (source.name === 'gold') {
      child.material.color.set(color === 'w' ? 0xb59d6d : 0x6f8c64)
      child.material.metalness = .15
    }
  })
  if (type === 'n') root.rotation.y = color === 'w' ? Math.PI : 0
  return root
}

function seek(target, animateMove = false) {
  target = Math.max(0, Math.min(game.moves.length, target))
  if (animateMove && !reducedMotion && target === ply + 1 && !animation) {
    animateTo(target)
  } else {
    animation = null
    seekDirect(target)
    if (playing) scheduleNext(comparisonFor(game.moves[target - 1])
      ? INTERVENTION_PREVIEW_MS + INTERVENTION_MOVE_MS + INTERVENTION_PAUSE_MS
      : NORMAL_MOVE_MS + NORMAL_PAUSE_MS)
  }
}

function seekDirect(target) {
  replay = new Chess(game.initial_fen || undefined)
  for (let i = 0; i < target; i++) applyUci(replay, game.moves[i].uci)
  ply = target
  renderPieces(replay)
  updateEffects()
  updateUi()
}

function animateTo(target) {
  const move = game.moves[target - 1]
  const from = move.uci.slice(0, 2)
  const to = move.uci.slice(2, 4)
  const object = pieceObjects.get(from)
  if (!object) return seekDirect(target)
  const start = object.position.clone()
  const endSquare = squarePosition(to)
  const end = new THREE.Vector3(endSquare.x, BOARD_TOP, endSquare.z)
  const comparison = comparisonFor(move)
  animation = { object, start, end, started: performance.now(),
    duration: comparison ? INTERVENTION_MOVE_MS : NORMAL_MOVE_MS,
    hold: comparison ? INTERVENTION_PREVIEW_MS : 0, target, hiddenCapture: false, to }
  showMoveEffects(move)
  updateJev(move)
}

function applyUci(chess, uci) {
  return chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] || 'q' })
}

function updateAnimation(now) {
  if (!animation) return
  const a = animation
  if (a.pausedAt != null) return
  const elapsed = now - a.started - a.hold
  if (elapsed < 0) return
  const raw = Math.min(1, elapsed / a.duration)
  const t = raw < .5 ? 2 * raw * raw : 1 - Math.pow(-2 * raw + 2, 2) / 2
  a.object.position.lerpVectors(a.start, a.end, t)
  a.object.position.y += Math.sin(Math.PI * t) * .024
  if (!a.hiddenCapture && raw > .42) {
    const captured = pieceObjects.get(a.to)
    if (captured && captured !== a.object) captured.visible = false
    a.hiddenCapture = true
  }
  if (raw >= 1) {
    const target = a.target
    animation = null
    seekDirect(target)
    if (playing) scheduleNext(comparisonFor(game.moves[target - 1]) ? INTERVENTION_PAUSE_MS : NORMAL_PAUSE_MS)
  }
}

function squarePosition(square) {
  const file = square.charCodeAt(0) - 97
  const rank = Number(square[1])
  return { x: (file - 3.5) * SQUARE, z: (4.5 - rank) * SQUARE }
}

function clearEffects() {
  effectRoot.traverse(object => {
    object.geometry?.dispose()
    object.material?.dispose()
  })
  effectRoot.clear()
}

function updateEffects() {
  clearEffects()
  if (ply === 0) return
  showMoveEffects(game.moves[ply - 1])
}

function showMoveEffects(move) {
  clearEffects()
  const actual = move.uci.slice(0, 4)
  addSquareGlow(actual.slice(0, 2), 0x467b69, .26)
  addSquareGlow(actual.slice(2, 4), 0x548e65, .5)
  const comparison = comparisonFor(move)
  if (comparison) {
    addMoveArc(comparison.base, 0x167897, .95, false, true)
    addMoveArc(comparison.selected, 0xe7a51b, 1, true)
    addDestination(comparison.base.slice(2, 4), 0x167897, false)
    addDestination(comparison.selected.slice(2, 4), 0xe7a51b, true)
    addPulse(comparison.selected.slice(2, 4), 0xe7a51b)
  } else {
    addMoveArc(actual, 0x386f77, .75, false)
  }
}

function comparisonFor(move) {
  if (!move) return null
  const decision = decisionFor(move)
  if (isJevActive(decision) && decision.intervention === true && decision.base_move && decision.base_move !== decision.selected_move) {
    return { base: decision.base_move, selected: decision.selected_move }
  }
  return fxPreview && !decision ? previewMoves(move.uci) : null
}

function addDestination(square, color, selected) {
  const p = squarePosition(square)
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(.019, .023, 48),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: .95, depthTest: false, depthWrite: false })
  )
  ring.rotation.x = -Math.PI / 2
  ring.position.set(p.x, BOARD_TOP + .003, p.z)
  ring.renderOrder = selected ? 16 : 13
  effectRoot.add(ring)
}

function addSquareGlow(square, color, opacity) {
  const p = squarePosition(square)
  const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false, blending: THREE.NormalBlending })
  const mesh = new THREE.Mesh(new THREE.RingGeometry(.012, .026, 32), mat)
  mesh.rotation.x = -Math.PI / 2
  mesh.position.set(p.x, BOARD_TOP + .0015, p.z)
  effectRoot.add(mesh)
}

function addMoveArc(uci, color, opacity, elevated, dashed = false) {
  if (!uci || uci.length < 4) return
  const a = squarePosition(uci.slice(0, 2))
  const b = squarePosition(uci.slice(2, 4))
  const start = new THREE.Vector3(a.x, BOARD_TOP + .008, a.z)
  const end = new THREE.Vector3(b.x, BOARD_TOP + .008, b.z)
  const mid = start.clone().add(end).multiplyScalar(.5)
  mid.y += elevated ? .062 : .035
  const curve = new THREE.QuadraticBezierCurve3(start, mid, end)
  const radius = elevated ? .0044 : dashed ? .0028 : .00145
  const material = new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthTest: false, depthWrite: false })
  const segments = dashed ? Math.max(4, Math.ceil(curve.getLength() / .015)) : 1
  for (let i = 0; i < segments; i++) {
    const begin = i / segments
    const finish = dashed ? (i + .58) / segments : 1
    const section = new THREE.CatmullRomCurve3(Array.from({ length: 12 }, (_, j) => curve.getPoint(begin + (finish - begin) * j / 11)))
    // A thin ivory outline keeps both paths readable over dark and light squares.
    const outline = new THREE.Mesh(new THREE.TubeGeometry(section, 16, radius + .001, 8, false),
      new THREE.MeshBasicMaterial({ color: 0xfff9e6, transparent: true, opacity: .9, depthTest: false, depthWrite: false }))
    outline.renderOrder = elevated ? 20 : 10
    effectRoot.add(outline)
    const tube = new THREE.Mesh(new THREE.TubeGeometry(section, 16, radius, 8, false), material.clone())
    tube.renderOrder = elevated ? 21 : 11
    effectRoot.add(tube)
  }
  const tangent = curve.getTangent(1).normalize()
  const cone = new THREE.Mesh(new THREE.ConeGeometry(elevated ? .010 : .007, .022, 20), material)
  cone.position.copy(end)
  cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tangent)
  cone.renderOrder = elevated ? 22 : 12
  effectRoot.add(cone)
}

function addPulse(square, color) {
  const p = squarePosition(square)
  const count = 80
  const positions = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2
    const radius = .014 + Math.random() * .035
    positions[i * 3] = p.x + Math.cos(angle) * radius
    positions[i * 3 + 1] = BOARD_TOP + .003 + Math.random() * .055
    positions[i * 3 + 2] = p.z + Math.sin(angle) * radius
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  const material = new THREE.PointsMaterial({ color, size: .004, transparent: true, opacity: .82, blending: THREE.NormalBlending, depthWrite: false })
  const particles = new THREE.Points(geometry, material)
  particles.userData.pulse = true
  effectRoot.add(particles)
}

function decisionFor(move) {
  return move?.jev || move?.decision || null
}

function isJevActive(decision) {
  return Boolean(decision?.selected_move && !decision.error && decision.enabled !== false)
}

function previewMoves(actual) {
  // Use another legal move from the same pre-move position for the visual preview.
  const position = new Chess(game.initial_fen || undefined)
  const index = animation ? animation.target - 1 : Math.max(0, ply - 1)
  for (let i = 0; i < index; i++) applyUci(position, game.moves[i].uci)
  const alternatives = position.moves({ verbose: true }).map(m => m.from + m.to + (m.promotion || ''))
  const base = alternatives.find(m => m !== actual && m.slice(0, 2) === actual.slice(0, 2))
    || alternatives.find(m => m !== actual) || actual
  return { base, selected: actual }
}

function updateUi() {
  const move = ply ? game.moves[ply - 1] : null
  els.timeline.value = String(ply)
  els.timeline.style.setProperty('--progress', `${game.moves.length ? ply / game.moves.length * 100 : 0}%`)
  els['timeline-time'].textContent = `${ply}수`
  updateJev(move)
}

function updateJev(move) {
  const decision = decisionFor(move)
  const preview = Boolean(fxPreview && move && !decision)
  const active = isJevActive(decision)
  const intervened = active && decision.intervention === true
  const state = preview ? 'preview' : intervened ? 'intervened' : active ? 'active' : 'inactive'
  els['jev-panel'].dataset.state = state
  els['jev-state'].textContent = preview || intervened ? 'Jev 개입' : active ? 'Jev 활성' : 'Jev 비활성'
  els['visual-badge'].hidden = !preview
  els['share-frame'].dataset.jev = state
  const comparison = comparisonFor(move)
  els['route-comparison'].hidden = !comparison
  if (comparison) {
    const label = uci => `${uci.slice(0, 2)} → ${uci.slice(2, 4)}${uci[4] ? '='+uci[4].toUpperCase() : ''}`
    els['route-base-move'].textContent = label(comparison.base)
    els['route-selected-move'].textContent = label(comparison.selected)
  }
}

function bindControls() {
  els['prev-button'].addEventListener('click', () => { stopPlayback(); seek(ply - 1) })
  els['next-button'].addEventListener('click', () => { stopPlayback(); seek(ply + 1, true) })
  els['play-button'].addEventListener('click', togglePlayback)
  els.timeline.addEventListener('input', () => { stopPlayback(); seek(Number(els.timeline.value)) })
  els['game-select'].addEventListener('change', event => selectGame(event.target.value))
  els['fx-button'].addEventListener('click', () => {
    fxPreview = !fxPreview
    els['fx-button'].classList.toggle('active', fxPreview)
    els['fx-button'].textContent = fxPreview ? '✳ 효과 예시 끄기' : '✳ 효과 미리보기'
    els['fx-button'].setAttribute('aria-pressed', String(fxPreview))
    if (fxPreview && ply === 0) seekDirect(1)
    updateEffects()
    updateJev(ply ? game.moves[ply - 1] : null)
  })
  els['camera-button'].addEventListener('click', flipCamera)
  els['fullscreen-button'].addEventListener('click', () => {
    if (document.fullscreenElement) document.exitFullscreen()
    else document.querySelector('.capture-wrap').requestFullscreen()
  })
  els['export-button'].addEventListener('click', exportPortrait)
  window.addEventListener('keydown', event => {
    if (!ready || exporting || /INPUT|SELECT|TEXTAREA|BUTTON/.test(event.target.tagName)) return
    if (event.code === 'Space') { event.preventDefault(); togglePlayback() }
    if (event.key === 'ArrowRight') { stopPlayback(); seek(ply + 1, true) }
    if (event.key === 'ArrowLeft') { stopPlayback(); seek(ply - 1) }
  })
}

function togglePlayback() {
  if (!ready || exporting) return
  if (playing) return stopPlayback()
  if (ply >= game.moves.length) seekDirect(0)
  playing = true
  els['play-button'].textContent = 'Ⅱ'
  els['play-button'].setAttribute('aria-label', '일시정지')
  if (animation) {
    if (animation.pausedAt != null) {
      animation.started += performance.now() - animation.pausedAt
      animation.pausedAt = null
    }
  } else {
    scheduleNext(90)
  }
}

function scheduleNext(delay = NORMAL_PAUSE_MS) {
  clearTimeout(playTimer)
  if (!playing) return
  if (ply >= game.moves.length) return stopPlayback()
  playTimer = setTimeout(() => seek(ply + 1, true), delay)
}

function stopPlayback() {
  playing = false
  if (animation && animation.pausedAt == null) animation.pausedAt = performance.now()
  clearTimeout(playTimer)
  playTimer = null
  els['play-button'].textContent = '▶'
  els['play-button'].setAttribute('aria-label', '재생')
}

function flipCamera() {
  cameraPreset = (cameraPreset + 1) % 3
  const positions = [[0, .9, .5], [0, 1, .001], [.38, .75, .40]]
  camera.position.set(...positions[cameraPreset])
  camera.zoom = cameraPreset === 2 ? .78 : 1
  camera.updateProjectionMatrix()
  controls.target.set(0, .014, 0)
  controls.update()
}

function setReady(value) {
  ready = value
  document.querySelectorAll('button, select, input').forEach(element => { element.disabled = !value })
}

async function exportPortrait() {
  if (!ready || exporting) return
  exporting = true
  stopPlayback()
  if (animation) { const target = animation.target; animation = null; seekDirect(target) }
  setReady(false)
  els['export-status'].textContent = '1080 × 1920 이미지 준비 중…'
  try {
    const { toCanvas } = await import('html-to-image')
    // Render the WebGL canvas at export resolution before taking the DOM snapshot.
    renderer.setPixelRatio(1080 / els['share-frame'].getBoundingClientRect().width)
    renderer.render(scene, camera)
    const width = els['share-frame'].getBoundingClientRect().width
    const snapshot = await toCanvas(els['share-frame'], {
      pixelRatio: 1080 / width, width, height: width * 16 / 9,
      backgroundColor: '#faf9f5', skipFonts: true, style: { boxShadow: 'none' }
    })
    const output = document.createElement('canvas')
    output.width = 1080
    output.height = 1920
    output.getContext('2d').drawImage(snapshot, 0, 0, 1080, 1920)
    const link = document.createElement('a')
    link.download = `jev-chess-${game.game}-${ply}${fxPreview ? '-visual-preview' : ''}.png`
    link.href = output.toDataURL('image/png')
    link.click()
    els['export-status'].textContent = '1080 × 1920 PNG 저장 완료'
  } catch (error) {
    console.error(error)
    els['export-status'].textContent = '이미지를 저장하지 못했습니다. 다시 시도해 주세요.'
  } finally {
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    exporting = false
    setReady(true)
  }
}

function animate(now) {
  requestAnimationFrame(animate)
  if (!exporting) controls.update()
  updateAnimation(now)
  for (const child of effectRoot.children) {
    if (child.userData.pulse) {
      if (!reducedMotion) child.position.y = Math.sin(now * .004) * .003
      child.material.opacity = .54 + Math.sin(now * .006) * .27
    }
  }
  renderer.render(scene, camera)
}

function resize() {
  const width = Math.max(1, els.scene.clientWidth)
  const height = Math.max(1, els.scene.clientHeight)
  const aspect = width / height
  camera.left = -VIEW_HALF_SIZE * aspect
  camera.right = VIEW_HALF_SIZE * aspect
  camera.updateProjectionMatrix()
  renderer.setSize(width, height, false)
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]))
}
