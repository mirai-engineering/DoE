import { useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Line, OrbitControls, Text } from '@react-three/drei'
import * as THREE from 'three'

const GRID = 14
const SPACING = 0.32
const TOTAL_POINTS = GRID * GRID

function surfaceZ(x: number, y: number, perfMod = 1, durMod = 0.5) {
  return Math.sin(x * 1.6 + perfMod * 0.5) * Math.cos(y * 1.6 + durMod * 0.3) * 0.35 + 0.05
}

function ChamberPoints({ stageIdx, stageT }: { stageIdx: number; stageT: number; progress: number }) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const color = useMemo(() => new THREE.Color(), [])

  const data = useMemo(() => {
    const off = ((GRID - 1) * SPACING) / 2
    return Array.from({ length: TOTAL_POINTS }, (_, i) => {
      const ix = i % GRID
      const iy = Math.floor(i / GRID)
      const gx = ix * SPACING - off
      const gy = iy * SPACING - off
      const z = surfaceZ(gx, gy)
      const score = gx * 0.5 + gy * 0.4 + z * 0.6 + 0.5
      const distChamp = Math.hypot(gx - 0.8, gy - 0.5)
      return { ix, iy, gx, gy, z, score, distChamp }
    })
  }, [])

  useFrame(({ clock }) => {
    if (!meshRef.current) return
    const elapsed = clock.getElapsedTime()
    const structProgress = stageIdx === 0 ? 0 : Math.min(1, (stageIdx - 1 + stageT) / 2)
    const ease = structProgress * structProgress * (3 - 2 * structProgress)

    for (let i = 0; i < TOTAL_POINTS; i += 1) {
      const d = data[i]
      const perfMod = stageIdx >= 3 ? 0.65 + Math.sin(elapsed * 0.15 + d.ix * 0.3) * 0.08 : 1
      const z = surfaceZ(d.gx, d.gy, perfMod, stageIdx >= 3 ? 0.25 + Math.cos(elapsed * 0.2 + d.iy * 0.3) * 0.06 : 0.5)

      const scatterX = d.gx + Math.sin(d.ix * 7.3 + d.iy * 5.1) * 0.6 + Math.cos(d.ix * 3.7 + d.iy * 9.2) * 0.4
      const scatterZ = d.gy + Math.cos(d.ix * 4.1 + d.iy * 6.3) * 0.6 + Math.sin(d.ix * 8.9 + d.iy * 2.3) * 0.4
      const scatterY = z + Math.sin(d.ix * 5.7 + d.iy * 3.9) * 0.4
      const fx = scatterX + (d.gx - scatterX) * ease
      const fy = scatterY + (z - scatterY) * ease
      const fz = scatterZ + (d.gy - scatterZ) * ease
      const drift = stageIdx === 0 ? Math.sin(elapsed * 0.5 + i * 0.1) * 0.03 : Math.sin(elapsed * 0.2 + i * 0.05) * 0.005
      const champion = stageIdx >= 4 && d.distChamp < 0.25
      const pulse = champion ? 1 + Math.sin(elapsed * 2.5) * 0.3 : 1
      const size = champion ? 0.18 : stageIdx >= 4 && d.score > 1 ? 0.08 : stageIdx >= 3 && d.score > 1.1 ? 0.1 : stageIdx >= 1 ? 0.06 : 0.08

      if (champion) color.set('#7C5CFF')
      else if (stageIdx >= 4 && d.score > 1) color.set('#63D7FF')
      else if (stageIdx >= 3 && d.score > 0.9) color.set('#7C5CFF')
      else color.set('#3B82F6')

      dummy.position.set(fx + drift, fy + (champion ? Math.sin(elapsed * 2 + d.ix) * 0.02 : 0), fz + drift)
      dummy.scale.setScalar(size * pulse)
      dummy.updateMatrix()
      meshRef.current.setMatrixAt(i, dummy.matrix)
      meshRef.current.setColorAt?.(i, color)
    }
    meshRef.current.instanceMatrix.needsUpdate = true
    if (meshRef.current.instanceColor) meshRef.current.instanceColor.needsUpdate = true
  })

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, TOTAL_POINTS]}>
      <sphereGeometry args={[1, 12, 8]} />
      <meshPhysicalMaterial color="white" emissive="#6D5DFB" emissiveIntensity={0.12} metalness={0.1} roughness={0.3} transparent opacity={0.9} />
    </instancedMesh>
  )
}

function ChamberSurface({ stageIdx, stageT }: { stageIdx: number; stageT: number; progress: number }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const surfAlpha = stageIdx >= 2 ? Math.min(0.3, (stageIdx - 2 + stageT) * 0.35) : 0

  useFrame(({ clock }) => {
    if (!meshRef.current) return
    const geometry = meshRef.current.geometry
    const position = geometry.attributes.position
    const elapsed = clock.getElapsedTime()
    for (let i = 0; i < position.count; i += 1) {
      const x = position.getX(i)
      const z = position.getZ(i)
      const perfMod = stageIdx >= 3 ? 0.65 + Math.sin(elapsed * 0.12 + x * 0.5) * 0.08 : 1
      const durMod = stageIdx >= 3 ? 0.25 + Math.cos(elapsed * 0.15 + z * 0.5) * 0.06 : 0.5
      position.setY(i, surfaceZ(x, z, perfMod, durMod))
    }
    position.needsUpdate = true
    geometry.computeVertexNormals()
  })

  if (surfAlpha < 0.01) return null
  return (
    <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]}>
      <planeGeometry args={[3.8, 3.8, 40, 40]} />
      <meshPhysicalMaterial color="#3B82F6" transparent opacity={surfAlpha} side={THREE.DoubleSide} metalness={0.05} roughness={0.5} emissive="#6D5DFB" emissiveIntensity={0.03} />
    </mesh>
  )
}

function ChamberAxes({ stageIdx, stageT }: { stageIdx: number; stageT: number }) {
  if (stageIdx < 1) return null
  const alpha = stageIdx === 1 ? Math.min(1, stageT * 2) * 0.35 : 0.35
  return (
    <group>
      <gridHelper args={[4.5, 10, new THREE.Color('#3B82F6'), new THREE.Color('#3B82F6')]} position={[0, -0.35, 0]} />
      <Line points={[[-1.5, -0.3, -1.5], [1.8, -0.3, -1.5]]} color="#3B82F6" lineWidth={1} transparent opacity={alpha} />
      <Line points={[[-1.5, -0.3, -1.5], [-1.5, -0.3, 1.8]]} color="#3B82F6" lineWidth={1} transparent opacity={alpha} />
      <Line points={[[-1.5, -0.3, -1.5], [-1.5, 0.8, -1.5]]} color="#3B82F6" lineWidth={1} transparent opacity={alpha} />
      <Text position={[1.7, -0.55, -1.5]} fontSize={0.13} color="#5A6B89" anchorX="right">Catalyst loading</Text>
      <Text position={[-1.5, -0.55, 1.7]} fontSize={0.13} color="#5A6B89" anchorX="right">Humidity</Text>
      <Text position={[-1.5, 0.95, -1.5]} fontSize={0.13} color="#5A6B89" anchorX="right">Voltage</Text>
    </group>
  )
}

function NeuralGraph({ stageIdx, stageT }: { stageIdx: number; stageT: number }) {
  const nodes = useMemo(() => Array.from({ length: 10 }, (_, i) => new THREE.Vector3(Math.sin(i * 2.1) * 1.1, 0.1 + ((i * 37) % 8) / 10, Math.cos(i * 1.7) * 1.1)), [])
  const edges = useMemo<[THREE.Vector3, THREE.Vector3][]>(() => nodes.flatMap((a, i) => nodes.slice(i + 1).filter((_, j) => (i + j) % 3 === 0).map((b) => [a, b] as [THREE.Vector3, THREE.Vector3])), [nodes])
  if (stageIdx < 2 || stageIdx >= 4) return null
  const alpha = stageIdx === 2 ? Math.min(0.08, stageT * 0.3) : 0.04
  return <group>{edges.map(([a, b], i) => <Line key={i} points={[a, b]} color="#6D5DFB" lineWidth={0.3} transparent opacity={alpha} />)}</group>
}

function ObjectiveSliders({ stageIdx, stageT }: { stageIdx: number; stageT: number }) {
  if (stageIdx < 3) return null
  const alpha = stageIdx === 3 ? Math.min(1, stageT * 2) * 0.5 : 0.5
  const objectives = [{ label: 'Performance', val: 0.65, color: '#7C5CFF' }, { label: 'Durability', val: 0.25, color: '#3B82F6' }, { label: 'Cost', val: 0.1, color: '#63D7FF' }]
  return <group position={[1.9, 0, -1.4]}>{objectives.map((obj, i) => <group key={obj.label} position={[0, i * 0.5, 0]}><mesh><boxGeometry args={[0.03, 0.45, 0.02]} /><meshBasicMaterial color="#3B82F6" transparent opacity={alpha * 0.15} /></mesh><mesh position={[0, -0.225 + obj.val * 0.45, 0]}><boxGeometry args={[0.05, obj.val * 0.45, 0.025]} /><meshBasicMaterial color={obj.color} transparent opacity={alpha * 0.5} /></mesh><Text position={[0.25, 0.08, 0]} fontSize={0.07} color="#5A6B89" anchorX="left">{obj.label}</Text></group>)}</group>
}

function ChampionMarker({ stageIdx }: { stageIdx: number }) {
  if (stageIdx < 4) return null
  return <group position={[0.8, 0.2, 0.5]}><mesh rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[0.15, 0.28, 32]} /><meshBasicMaterial color="#7C5CFF" transparent opacity={0.35} side={THREE.DoubleSide} /></mesh></group>
}

function RecommendationCard({ stageIdx, stageT }: { stageIdx: number; stageT: number }) {
  if (stageIdx < 4) return null
  const alpha = Math.min(1, stageT * 2)
  return (
    <group position={[1.3, 0.6, 0.8]}>
      <mesh><planeGeometry args={[0.85, 0.75]} /><meshBasicMaterial color="#0A1630" transparent opacity={0.85 * alpha} /></mesh>
      <Text position={[-0.35, 0.23, 0.01]} fontSize={0.05} color="#6D5DFB" anchorX="left">RECOMMENDED RUN</Text>
      <Text position={[-0.35, 0.1, 0.01]} fontSize={0.12} color="#F6F4EA" anchorX="left">C-017</Text>
      <Text position={[-0.35, -0.03, 0.01]} fontSize={0.05} color="#63D7FF" anchorX="left">HIGH CONFIDENCE</Text>
      <Text position={[-0.35, -0.18, 0.01]} fontSize={0.05} color="#7C5CFF" anchorX="left">Performance +12.6%</Text>
    </group>
  )
}

function CameraController({ progress, stageIdx }: { progress: number; stageIdx: number }) {
  useFrame(({ camera }) => {
    const zoomProgress = Math.max(0, Math.min(1, (progress - 0.78) / 0.18))
    const easeZoom = zoomProgress * zoomProgress * (3 - 2 * zoomProgress)
    const theta = -0.35 + easeZoom * -0.15
    const phi = 0.5 + easeZoom * -0.15
    const dist = 4.8 - easeZoom * 1.8
    camera.position.set(Math.sin(theta) * Math.cos(phi) * dist, Math.sin(phi) * dist + (stageIdx >= 4 ? easeZoom * 0.15 : 0), Math.cos(theta) * Math.cos(phi) * dist)
    camera.lookAt(0, stageIdx >= 4 ? 0.15 : 0, 0)
  })
  return null
}

export default function ExperimentChamber({ progress, stageIdx, stageT, reduce }: { progress: number; stageIdx: number; stageT: number; reduce: boolean }) {
  const safeProgress = reduce ? 0.85 : progress
  return (
    <Canvas camera={{ position: [3.5, 2.2, 3.8], fov: 38, near: 0.1, far: 15 }} dpr={[1, 2]} gl={{ antialias: true, alpha: true }} style={{ width: '100%', height: '100%', background: 'radial-gradient(ellipse at 60% 50%, #061226 0%, #030716 100%)' }}>
      <ambientLight intensity={0.5} color="#3B82F6" />
      <pointLight position={[2, 4, 3]} intensity={0.6} color="#6D5DFB" />
      <pointLight position={[-2, 1, -2]} intensity={0.2} color="#3B82F6" />
      <directionalLight position={[0, 3, 0]} intensity={0.15} color="#63D7FF" />
      <group position={[0, -0.1, 0]}>
        <ChamberPoints stageIdx={stageIdx} stageT={stageT} progress={safeProgress} />
        <ChamberSurface stageIdx={stageIdx} stageT={stageT} progress={safeProgress} />
        <ChamberAxes stageIdx={stageIdx} stageT={stageT} />
        <NeuralGraph stageIdx={stageIdx} stageT={stageT} />
        <ObjectiveSliders stageIdx={stageIdx} stageT={stageT} />
        <ChampionMarker stageIdx={stageIdx} />
        <RecommendationCard stageIdx={stageIdx} stageT={stageT} />
      </group>
      <CameraController progress={safeProgress} stageIdx={stageIdx} />
      {safeProgress > 0.95 && <OrbitControls enableZoom={false} enablePan={false} rotateSpeed={0.2} />}
    </Canvas>
  )
}
