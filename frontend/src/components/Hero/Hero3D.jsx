import React, { useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Float } from '@react-three/drei'
import { useThree } from '@react-three/fiber'

function GoldRing({ mouse }) {
  const meshRef = useRef()
  
  useFrame((state) => {
    if (meshRef.current) {
      // Smooth rotation animation
      meshRef.current.rotation.y += 0.003
      meshRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.3) * 0.1
      
      // Mouse parallax effect
      meshRef.current.position.x = 2.2 + mouse.current.x * 0.3
      meshRef.current.position.y = 1.4 + mouse.current.y * 0.2
    }
  })
  
  return (
    <Float speed={0.8} rotationIntensity={0.15} floatIntensity={0.25}>
      <mesh ref={meshRef} position={[2.2, 1.4, -0.7]} rotation={[0.18, 0.38, 0]}>
        <torusGeometry args={[0.85, 0.045, 24, 140]} />
        <meshStandardMaterial color="#E8C95A" metalness={0.6} roughness={0.42} />
      </mesh>
    </Float>
  )
}

function IvoryPanel({ position, rotation, opacity = 0.13, mouse }) {
  const meshRef = useRef()
  
  useFrame((state) => {
    if (meshRef.current) {
      // Subtle rotation
      meshRef.current.rotation.z = Math.sin(state.clock.elapsedTime * 0.4) * 0.05
      
      // Mouse parallax (slower than ring)
      meshRef.current.position.x = position[0] + mouse.current.x * 0.15
      meshRef.current.position.y = position[1] + mouse.current.y * 0.1
    }
  })
  
  return (
    <Float speed={0.6} rotationIntensity={0.08} floatIntensity={0.15}>
      <mesh ref={meshRef} position={position} rotation={rotation}>
        <planeGeometry args={[1.3, 0.8]} />
        <meshStandardMaterial color="#F7F2E6" transparent opacity={opacity} roughness={0.18} metalness={0.05} />
      </mesh>
    </Float>
  )
}

export default function Hero3D() {
  const mouse = useRef({ x: 0, y: 0 })
  
  const handleMouseMove = (e) => {
    const x = (e.clientX / window.innerWidth) * 2 - 1
    const y = -(e.clientY / window.innerHeight) * 2 + 1
    mouse.current = { x: x * 0.5, y: y * 0.5 }
  }
  
  return (
    <div 
      className="hero-3d" 
      aria-hidden="true"
      onMouseMove={handleMouseMove}
    >
      <Canvas camera={{ position: [0, 0, 5], fov: 50 }} dpr={[1, 1.5]}>
        <ambientLight intensity={0.85} />
        <directionalLight position={[3, 3, 2]} intensity={0.55} />
        <directionalLight position={[-3, -2, 2]} intensity={0.25} />

        {/* Dynamic ring with mouse parallax */}
        <GoldRing mouse={mouse} />
        {/* Interactive panels */}
        <IvoryPanel position={[-2.1, 0.8, -1.2]} rotation={[0, 0.18, 0]} opacity={0.13} mouse={mouse} />
        <IvoryPanel position={[1.3, -1.3, -1.3]} rotation={[0, -0.18, 0]} opacity={0.10} mouse={mouse} />
      </Canvas>
    </div>
  )
}
