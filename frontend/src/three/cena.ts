/**
 * Gemeo digital 3D das salas de vacina.
 *
 * Regras seguidas:
 *  - a cena muda SOMENTE com dados do store de tempo real (que vem do WebSocket);
 *  - nada e redesenhado a cada mensagem: o loop de animacao le o store;
 *  - repeticoes (frascos de vacina, cadeiras) usam InstancedMesh;
 *  - tubos e cabos ligam pontos de conexao exatos dos equipamentos.
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { COR_STATUS, dados, semDadosGlobal, statusDispositivo } from '../stores/tempoReal'
import type { Dispositivo, Status } from '../types'
import {
  ALTURA_SALA,
  centroGeladeira,
  centroSala,
  LARGURA_SALA,
  OFFSET_GELADEIRA,
  OFFSET_SALA,
  PROFUNDIDADE_SALA,
  somar,
  type Vec3,
} from './posicoes'

const BRANCO = 0xf4f7f9
const CORES_STATUS: Record<Status, THREE.Color> = {
  normal: new THREE.Color(COR_STATUS.normal),
  atencao: new THREE.Color(COR_STATUS.atencao),
  critico: new THREE.Color(COR_STATUS.critico),
  sem_dados: new THREE.Color(COR_STATUS.sem_dados),
}

interface Item {
  disp: Dispositivo
  indicadores: THREE.Mesh[]
  status: Status
}

interface Geladeira {
  gid: string
  porta: THREE.Group
  aberturaAtual: number
  nevoa: THREE.Points
  nevoaSaida: THREE.Points
  ventoinha?: THREE.Object3D
  ventoinhaAr?: THREE.Points
  compressorCorpo?: THREE.Object3D
  compressorBase?: THREE.Vector3
  alarmeLuz?: THREE.PointLight
  alarmeMesh?: THREE.Mesh
  ids: Record<string, string>
}

interface Sala {
  ubs: string
  janela: THREE.MeshBasicMaterial
  sol: THREE.DirectionalLight
  lampada: THREE.PointLight
  lampadaMesh: THREE.Mesh
  termometro: THREE.Mesh
  ids: Record<string, string>
}

function texturaTexto(texto: string, cor = '#0f2530'): THREE.SpriteMaterial {
  const c = document.createElement('canvas')
  c.width = 512
  c.height = 96
  const g = c.getContext('2d')!
  g.fillStyle = 'rgba(255,255,255,0.88)'
  g.beginPath()
  g.roundRect(4, 4, 504, 88, 22)
  g.fill()
  g.fillStyle = cor
  g.font = 'bold 42px Segoe UI, sans-serif'
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillText(texto, 256, 50)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return new THREE.SpriteMaterial({ map: t, depthTest: false })
}

function v(p: Vec3) {
  return new THREE.Vector3(...p)
}

export class CenaGemeo {
  private renderer: THREE.WebGLRenderer
  private cena = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private controles: OrbitControls
  private raio = new THREE.Raycaster()
  private relogio = new THREE.Clock()
  private raf = 0
  private grupo = new THREE.Group()
  private itens = new Map<string, Item>()
  private clicaveis: THREE.Object3D[] = []
  private geladeiras: Geladeira[] = []
  private salas: Sala[] = []
  private hemi: THREE.HemisphereLight
  private ultimoStatus = 0
  private observador: ResizeObserver
  private inicioToque = { x: 0, y: 0 }
  selecionado: string | null = null
  private alvo: HTMLElement
  private aoSelecionar: (id: string | null) => void

  constructor(alvo: HTMLElement, aoSelecionar: (id: string | null) => void) {
    this.alvo = alvo
    this.aoSelecionar = aoSelecionar
    this.renderer = new THREE.WebGLRenderer({ antialias: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    alvo.appendChild(this.renderer.domElement)

    this.camera = new THREE.PerspectiveCamera(45, 1, 0.1, 200)
    this.camera.position.set(0, 13, 17)
    this.controles = new OrbitControls(this.camera, this.renderer.domElement)
    this.controles.target.set(0, 1, -1)
    this.controles.maxPolarAngle = Math.PI * 0.48
    this.controles.minDistance = 4
    this.controles.maxDistance = 45
    this.controles.enableDamping = true

    this.cena.background = new THREE.Color(0xdfe8ee)
    this.hemi = new THREE.HemisphereLight(0xffffff, 0x8899aa, 0.8)
    this.cena.add(this.hemi)
    this.cena.add(this.grupo)

    const el = this.renderer.domElement
    el.addEventListener('pointerdown', (e) => (this.inicioToque = { x: e.clientX, y: e.clientY }))
    el.addEventListener('pointerup', (e) => this.clique(e))

    this.observador = new ResizeObserver(() => this.redimensionar())
    this.observador.observe(alvo)
    this.redimensionar()
    this.animar()
  }

  // ------------------------------------------------------------------ montagem
  montar(dispositivos: Dispositivo[]) {
    this.grupo.clear()
    this.itens.clear()
    this.clicaveis = []
    this.geladeiras = []
    this.salas = []
    const ativos = dispositivos.filter((d) => d.ativo)
    const ubsList = [...new Set(ativos.map((d) => d.ubs))].sort()
    for (const ubs of ubsList) {
      const daUbs = ativos.filter((d) => d.ubs === ubs)
      this.montarSala(ubs, ubsList, daUbs.filter((d) => !d.geladeira))
      const gids = [...new Set(daUbs.map((d) => d.geladeira).filter((g): g is string => !!g))].sort()
      for (const gid of gids) {
        this.montarGeladeira(gid, ubs, ubsList, gids, daUbs.filter((d) => d.geladeira === gid))
      }
    }
    // fileira de cadeiras da sala de espera (InstancedMesh)
    const cadeiraGeo = new THREE.BoxGeometry(0.5, 0.45, 0.5)
    const cadeiraMat = new THREE.MeshStandardMaterial({ color: 0x5b8fa8 })
    const porSala = 8
    const cadeiras = new THREE.InstancedMesh(cadeiraGeo, cadeiraMat, porSala * ubsList.length)
    const m = new THREE.Matrix4()
    ubsList.forEach((ubs, i) => {
      const c = centroSala(ubs, ubsList)
      for (let k = 0; k < porSala; k++) {
        m.makeTranslation(c[0] - 3.5 + k * 1.0, 0.225, 3.2)
        cadeiras.setMatrixAt(i * porSala + k, m)
      }
    })
    cadeiras.castShadow = true
    this.grupo.add(cadeiras)
  }

  private registrar(disp: Dispositivo | undefined, ...meshes: THREE.Mesh[]) {
    if (!disp) return
    for (const mesh of meshes) {
      mesh.userData.id = disp.id
      this.clicaveis.push(mesh)
    }
    const atual = this.itens.get(disp.id)
    if (atual) atual.indicadores.push(...meshes)
    else this.itens.set(disp.id, { disp, indicadores: meshes, status: 'sem_dados' })
  }

  private montarSala(ubs: string, ubsList: string[], disps: Dispositivo[]) {
    const c = v(centroSala(ubs, ubsList))
    const g = new THREE.Group()
    g.position.copy(c)
    this.grupo.add(g)

    // piso (ladrilhos), paredes do fundo e lateral com janela
    const piso = new THREE.Mesh(
      new THREE.BoxGeometry(LARGURA_SALA, 0.1, PROFUNDIDADE_SALA),
      new THREE.MeshStandardMaterial({ color: 0xcfd8dc }),
    )
    piso.position.y = -0.05
    piso.receiveShadow = true
    g.add(piso)
    const matParede = new THREE.MeshStandardMaterial({ color: 0xeef3f5 })
    const fundo = new THREE.Mesh(new THREE.BoxGeometry(LARGURA_SALA, ALTURA_SALA, 0.15), matParede)
    fundo.position.set(0, ALTURA_SALA / 2, -PROFUNDIDADE_SALA / 2)
    fundo.receiveShadow = true
    g.add(fundo)
    const lateral = new THREE.Mesh(new THREE.BoxGeometry(0.15, ALTURA_SALA, PROFUNDIDADE_SALA), matParede)
    lateral.position.set(-LARGURA_SALA / 2, ALTURA_SALA / 2, 0)
    g.add(lateral)
    // janela: a cor do "ceu" acompanha a luminosidade medida (dia/noite)
    const janelaMat = new THREE.MeshBasicMaterial({ color: 0x9bd3ff })
    const janela = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 1.5), janelaMat)
    janela.rotation.y = Math.PI / 2
    janela.position.set(-LARGURA_SALA / 2 + 0.09, 2.3, -2.8 + 2.8)
    g.add(janela)
    const moldura = new THREE.Mesh(
      new THREE.BoxGeometry(0.05, 1.62, 2.72),
      new THREE.MeshStandardMaterial({ color: 0x64748b, wireframe: true }),
    )
    moldura.position.copy(janela.position)
    g.add(moldura)

    const sol = new THREE.DirectionalLight(0xfff4d6, 1.2)
    sol.position.set(c.x - 12, 9, c.z + 2)
    sol.target.position.copy(c)
    sol.castShadow = true
    sol.shadow.mapSize.set(1024, 1024)
    sol.shadow.camera.left = -8
    sol.shadow.camera.right = 8
    sol.shadow.camera.top = 8
    sol.shadow.camera.bottom = -8
    this.grupo.add(sol, sol.target)

    const titulo = new THREE.Sprite(texturaTexto(ubs === 'ubs01' ? 'UBS Centro' : ubs === 'ubs02' ? 'UBS Vila Nova' : ubs))
    titulo.scale.set(3.2, 0.6, 1)
    titulo.position.set(0, ALTURA_SALA + 0.6, -PROFUNDIDADE_SALA / 2)
    g.add(titulo)

    const por = (gr: string) => disps.find((d) => d.grandeza === gr)

    // termometro de parede (temperatura da sala): coluna sobe com a temperatura
    const tamb = por('temp_ambiente')
    const pTamb = v(OFFSET_SALA.temp_ambiente)
    const tuboVidro = new THREE.Mesh(
      new THREE.CylinderGeometry(0.09, 0.09, 1.2, 16),
      new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: 0.45 }),
    )
    tuboVidro.position.copy(pTamb)
    const coluna = new THREE.Mesh(
      new THREE.CylinderGeometry(0.055, 0.055, 1, 12),
      new THREE.MeshStandardMaterial({ color: 0xdc2626, emissive: 0x330000 }),
    )
    coluna.position.set(pTamb.x + 0.01, pTamb.y - 0.6, pTamb.z)
    coluna.geometry.translate(0, 0.5, 0)
    const bulbo = new THREE.Mesh(new THREE.SphereGeometry(0.13, 16, 12), new THREE.MeshStandardMaterial({ color: 0x94a3b8 }))
    bulbo.position.set(pTamb.x, pTamb.y - 0.7, pTamb.z)
    g.add(tuboVidro, coluna, bulbo)
    this.registrar(tamb, bulbo, tuboVidro)

    // sensor de luminosidade (cupula ao lado da janela)
    const lux = por('luminosidade')
    const cupula = new THREE.Mesh(
      new THREE.SphereGeometry(0.16, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2),
      new THREE.MeshStandardMaterial({ color: 0x94a3b8 }),
    )
    cupula.rotation.z = -Math.PI / 2
    cupula.position.copy(v(OFFSET_SALA.luminosidade))
    g.add(cupula)
    this.registrar(lux, cupula)

    // luminaria do teto (atuador controlado pela Web)
    const luz = por('luz')
    const lampMesh = new THREE.Mesh(
      new THREE.CylinderGeometry(0.5, 0.6, 0.15, 24),
      new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0x000000 }),
    )
    lampMesh.position.copy(v(OFFSET_SALA.luz))
    const fio = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.25), new THREE.MeshStandardMaterial({ color: 0x333333 }))
    fio.position.set(lampMesh.position.x, ALTURA_SALA - 0.12, lampMesh.position.z)
    const lampada = new THREE.PointLight(0xfff1c1, 0, 14, 1.4)
    lampada.position.set(lampMesh.position.x, lampMesh.position.y - 0.3, lampMesh.position.z)
    g.add(lampMesh, fio, lampada)
    this.registrar(luz, lampMesh)

    this.salas.push({
      ubs,
      janela: janelaMat,
      sol,
      lampada,
      lampadaMesh: lampMesh,
      termometro: coluna,
      ids: { temp_ambiente: tamb?.id ?? '', luminosidade: lux?.id ?? '', luz: luz?.id ?? '' },
    })
  }

  private montarGeladeira(gid: string, ubs: string, ubsList: string[], gids: string[], disps: Dispositivo[]) {
    const base = centroGeladeira(gid, ubs, ubsList, gids)
    const g = new THREE.Group()
    g.position.copy(v(base))
    this.grupo.add(g)
    const por = (gr: string) => disps.find((d) => d.grandeza === gr)
    const W = 1.4,
      H = 2.2,
      D = 1.2,
      E = 0.06
    const matCorpo = new THREE.MeshStandardMaterial({ color: BRANCO, roughness: 0.5 })
    const matInterno = new THREE.MeshStandardMaterial({ color: 0xdbeafe, side: THREE.DoubleSide })

    // corpo aberto na frente (fundo, laterais, topo, base) para ver o interior com a porta aberta
    const paineis: [number, number, number, number, number, number][] = [
      [W, H, E, 0, H / 2, -D / 2 + E / 2],
      [E, H, D, -W / 2 + E / 2, H / 2, 0],
      [E, H, D, W / 2 - E / 2, H / 2, 0],
      [W, E, D, 0, H - E / 2, 0],
      [W, 0.12, D, 0, 0.06, 0],
    ]
    for (const [w, h, d, x, y, z] of paineis) {
      const p = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), matCorpo)
      p.position.set(x, y, z)
      p.castShadow = true
      p.receiveShadow = true
      g.add(p)
    }
    const interno = new THREE.Mesh(new THREE.BoxGeometry(W - 2 * E - 0.01, H - 0.2, D - E - 0.02), matInterno)
    interno.position.set(0, H / 2 + 0.02, 0.01)
    g.add(interno)

    // prateleiras + frascos de vacina (InstancedMesh)
    const prateleiras = [0.55, 1.05, 1.55]
    for (const y of prateleiras) {
      const pr = new THREE.Mesh(
        new THREE.BoxGeometry(W - 2 * E, 0.03, D - 0.15),
        new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: 0.7 }),
      )
      pr.position.set(0, y, 0)
      g.add(pr)
    }
    const porPrateleira = 14
    const frascos = new THREE.InstancedMesh(
      new THREE.CylinderGeometry(0.035, 0.035, 0.14, 8),
      new THREE.MeshStandardMaterial({ color: 0x7dd3fc }),
      prateleiras.length * porPrateleira,
    )
    const m4 = new THREE.Matrix4()
    let k = 0
    for (const y of prateleiras)
      for (let i = 0; i < porPrateleira; i++) {
        m4.makeTranslation(-0.55 + (i % 7) * 0.18, y + 0.085, -0.25 + Math.floor(i / 7) * 0.3)
        frascos.setMatrixAt(k++, m4)
      }
    g.add(frascos)

    // nevoa fria no interior: mais visivel quanto mais fria a geladeira
    const nevoa = this.particulas(60, 0xe0f2fe, 0.06, [W - 0.25, H - 0.4, D - 0.3], [0, H / 2, 0])
    g.add(nevoa)

    // porta (pivo na dobradica esquerda); clicar nela seleciona o sensor de porta
    const porta = new THREE.Group()
    porta.position.set(-W / 2, 0, D / 2)
    const folha = new THREE.Mesh(new THREE.BoxGeometry(W, H - 0.05, 0.07), matCorpo)
    folha.position.set(W / 2, H / 2, 0.035)
    folha.castShadow = true
    const puxador = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.6, 0.06), new THREE.MeshStandardMaterial({ color: 0x94a3b8 }))
    puxador.position.set(W - 0.12, 1.2, 0.1)
    porta.add(folha, puxador)
    g.add(porta)
    // ar frio saindo pela porta aberta
    const nevoaSaida = this.particulas(40, 0xf0f9ff, 0.07, [W, 0.6, 0.8], [0, 0.4, D / 2 + 0.4])
    g.add(nevoaSaida)

    // display de temperatura na porta (sensor de temperatura interna)
    const temp = por('temperatura')
    const display = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.2, 0.03), new THREE.MeshStandardMaterial({ color: 0x94a3b8 }))
    const oT = OFFSET_GELADEIRA.temperatura
    display.position.set(oT[0] + W / 2, oT[1], 0.085)
    porta.add(display)
    const sonda = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 8), new THREE.MeshStandardMaterial({ color: 0x94a3b8 }))
    sonda.position.set(0, 1.3, -0.3)
    g.add(sonda)
    this.registrar(temp, display, sonda)

    // sensor magnetico de porta
    const portaD = por('porta')
    const ima = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.18, 0.05), new THREE.MeshStandardMaterial({ color: 0x94a3b8 }))
    ima.position.set(W / 2 - 0.02, OFFSET_GELADEIRA.porta[1], D / 2 + 0.03)
    g.add(ima)
    this.registrar(portaD, ima)
    if (portaD) {
      folha.userData.id = portaD.id
      this.clicaveis.push(folha)
    }

    // sensor de umidade na lateral
    const umid = por('umidade')
    const sensorU = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.12, 14), new THREE.MeshStandardMaterial({ color: 0x94a3b8 }))
    sensorU.rotation.z = Math.PI / 2
    sensorU.position.set(...OFFSET_GELADEIRA.umidade)
    g.add(sensorU)
    this.registrar(umid, sensorU)

    // alarme sonoro (sinalizador no topo) - acionado pela regra de negocio
    const alarme = por('alarme')
    const sinal = new THREE.Mesh(
      new THREE.CylinderGeometry(0.1, 0.13, 0.22, 16),
      new THREE.MeshStandardMaterial({ color: 0x7f1d1d, emissive: 0x000000, transparent: true, opacity: 0.95 }),
    )
    sinal.position.set(...OFFSET_GELADEIRA.alarme)
    const alarmeLuz = new THREE.PointLight(0xff2222, 0, 4)
    alarmeLuz.position.set(sinal.position.x, sinal.position.y + 0.3, sinal.position.z)
    g.add(sinal, alarmeLuz)
    this.registrar(alarme, sinal)

    // resfriamento de emergencia: ventoinha no topo (gira quando ligada)
    const resfr = por('resfriamento')
    const oR = OFFSET_GELADEIRA.resfriamento
    const carcaca = new THREE.Mesh(
      new THREE.CylinderGeometry(0.32, 0.32, 0.14, 24, 1, true),
      new THREE.MeshStandardMaterial({ color: 0x94a3b8, side: THREE.DoubleSide }),
    )
    carcaca.position.set(...oR)
    const helice = new THREE.Group()
    helice.position.set(oR[0], oR[1], oR[2])
    for (let i = 0; i < 4; i++) {
      const pa = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.02, 0.08), new THREE.MeshStandardMaterial({ color: 0x334155 }))
      pa.position.x = 0.14
      const braco = new THREE.Group()
      braco.rotation.y = (i * Math.PI) / 2
      braco.add(pa)
      helice.add(braco)
    }
    const ventoinhaAr = this.particulas(30, 0xbae6fd, 0.05, [0.5, 0.5, 0.5], [oR[0], oR[1] + 0.3, oR[2]])
    g.add(carcaca, helice, ventoinhaAr)
    this.registrar(resfr, carcaca)

    // compressor: base fixa (pontos de conexao) + corpo que treme com a vibracao
    const comp = por('compressor')
    const oC = OFFSET_GELADEIRA.compressor
    const baseComp = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.1, 0.7), new THREE.MeshStandardMaterial({ color: 0x475569 }))
    baseComp.position.set(oC[0], 0.05, oC[2])
    const corpo = new THREE.Group()
    corpo.position.set(oC[0], 0.1, oC[2])
    const carcComp = new THREE.Mesh(
      new THREE.CylinderGeometry(0.28, 0.3, 0.55, 20),
      new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.4, roughness: 0.5 }),
    )
    carcComp.position.y = 0.3
    carcComp.castShadow = true
    const ledComp = new THREE.Mesh(new THREE.SphereGeometry(0.06, 12, 8), new THREE.MeshStandardMaterial({ color: 0x94a3b8 }))
    ledComp.position.set(0, 0.62, 0)
    corpo.add(carcComp, ledComp)
    // conectores fixos na base: tubo de gas (lado da geladeira) e cabo de energia (fundo)
    const conectorTubo = v([oC[0] - 0.32, 0.18, oC[2]])
    const conectorCabo = v([oC[0], 0.18, oC[2] - 0.3])
    const nub = (p: THREE.Vector3, cor: number) => {
      const n = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.16, 10), new THREE.MeshStandardMaterial({ color: cor }))
      n.position.copy(p)
      g.add(n)
    }
    nub(conectorTubo, 0xb87333)
    nub(conectorCabo, 0x111827)
    g.add(baseComp, corpo)
    this.registrar(comp, carcComp, ledComp)

    // tubo de gas refrigerante: do conector do compressor ate o conector na lateral da geladeira
    const entradaGeladeira = v([W / 2 + 0.02, 0.5, -D / 2 + 0.25])
    nub(entradaGeladeira, 0xb87333)
    const curvaTubo = new THREE.CatmullRomCurve3([
      conectorTubo,
      v([conectorTubo.x, 0.45, conectorTubo.z]),
      v([entradaGeladeira.x + 0.12, 0.5, entradaGeladeira.z]),
      entradaGeladeira,
    ])
    g.add(new THREE.Mesh(new THREE.TubeGeometry(curvaTubo, 32, 0.03, 8), new THREE.MeshStandardMaterial({ color: 0xb87333, metalness: 0.6 })))

    // cabo de energia: da tomada na parede do fundo ate o compressor
    const zParede = -PROFUNDIDADE_SALA / 2 + 0.08 - base[2]
    const tomadaPos = v([oC[0], 0.45, zParede + 0.03])
    const tomada = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.25, 0.06), new THREE.MeshStandardMaterial({ color: 0xffffff }))
    tomada.position.copy(tomadaPos)
    g.add(tomada)
    const inicioCabo = v([tomadaPos.x, tomadaPos.y, tomadaPos.z + 0.03])
    const curvaCabo = new THREE.CatmullRomCurve3([
      inicioCabo,
      v([inicioCabo.x, 0.08, inicioCabo.z + 0.15]),
      v([conectorCabo.x, 0.06, conectorCabo.z - 0.2]),
      conectorCabo,
    ])
    g.add(new THREE.Mesh(new THREE.TubeGeometry(curvaCabo, 32, 0.02, 6), new THREE.MeshStandardMaterial({ color: 0x111827 })))

    const rotulo = new THREE.Sprite(texturaTexto(gid.split('-')[1]?.toUpperCase() ?? gid))
    rotulo.scale.set(1.2, 0.23, 1)
    rotulo.position.set(0, H + 0.75, 0)
    g.add(rotulo)

    this.geladeiras.push({
      gid,
      porta,
      aberturaAtual: 0,
      nevoa,
      nevoaSaida,
      ventoinha: helice,
      ventoinhaAr,
      compressorCorpo: corpo,
      compressorBase: corpo.position.clone(),
      alarmeLuz,
      alarmeMesh: sinal,
      ids: Object.fromEntries(disps.map((d) => [d.grandeza, d.id])),
    })
  }

  private particulas(n: number, cor: number, tamanho: number, caixa: Vec3, centro: Vec3) {
    const pos = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) {
      pos[i * 3] = centro[0] + (Math.random() - 0.5) * caixa[0]
      pos[i * 3 + 1] = centro[1] + (Math.random() - 0.5) * caixa[1]
      pos[i * 3 + 2] = centro[2] + (Math.random() - 0.5) * caixa[2]
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    const p = new THREE.Points(
      geo,
      new THREE.PointsMaterial({ color: cor, size: tamanho, transparent: true, opacity: 0, depthWrite: false }),
    )
    p.userData = { centro, caixa }
    return p
  }

  // ------------------------------------------------------------------ atualizacao
  private atualizarStatus() {
    for (const item of this.itens.values()) {
      const s = statusDispositivo(item.disp)
      item.status = s
      const destaque = this.selecionado === item.disp.id
      for (const mesh of item.indicadores) {
        const mat = mesh.material as THREE.MeshStandardMaterial
        mat.color.copy(CORES_STATUS[s])
        if (mat.emissive && item.disp.grandeza !== 'alarme' && item.disp.grandeza !== 'luz') {
          mat.emissive.copy(CORES_STATUS[s]).multiplyScalar(destaque ? 0.8 : s === 'sem_dados' ? 0 : 0.35)
        }
      }
    }
  }

  private leitura(id: string | undefined) {
    if (!id) return undefined
    const l = dados.leituras.get(id)
    return l ? l.conteudo : undefined
  }

  private animar = () => {
    this.raf = requestAnimationFrame(this.animar)
    const dt = Math.min(this.relogio.getDelta(), 0.1)
    const t = this.relogio.elapsedTime
    const parado = semDadosGlobal()
    const agora = performance.now()
    if (agora - this.ultimoStatus > 500) {
      this.ultimoStatus = agora
      this.atualizarStatus()
    }

    for (const s of this.salas) {
      const lux = this.leitura(s.ids.luminosidade)?.valor as number | undefined
      const luzLigada = this.leitura(s.ids.luz)?.estado === 'ligado'
      const natural = parado || lux === undefined ? 0.5 : Math.min(1, Math.max(0, (lux - (luzLigada ? 350 : 0)) / 600))
      s.janela.color.setRGB(0.04 + 0.57 * natural, 0.08 + 0.75 * natural, 0.19 + 0.81 * natural)
      s.sol.intensity = 0.15 + 1.3 * natural
      s.lampada.intensity = luzLigada && !parado ? 6 : 0
      ;(s.lampadaMesh.material as THREE.MeshStandardMaterial).emissive.setHex(luzLigada && !parado ? 0xfff1c1 : 0x000000)
      const tamb = this.leitura(s.ids.temp_ambiente)?.valor as number | undefined
      const alvo = tamb === undefined ? 0.5 : Math.min(1.1, Math.max(0.05, (tamb - 15) / 20))
      s.termometro.scale.y += (alvo - s.termometro.scale.y) * Math.min(1, dt * 2)
    }
    const somaLuz = this.salas.reduce((a, s) => a + s.sol.intensity, 0) / Math.max(1, this.salas.length)
    this.hemi.intensity = 0.35 + somaLuz * 0.35

    for (const g of this.geladeiras) {
      const porta = this.leitura(g.ids.porta)?.valor === 1
      const temp = this.leitura(g.ids.temperatura)?.valor as number | undefined
      const comp = this.leitura(g.ids.compressor)
      const resfr = this.leitura(g.ids.resfriamento)?.estado === 'ligado'
      const alarme = this.leitura(g.ids.alarme)?.estado === 'ligado'

      const alvoPorta = porta && !parado ? 1 : 0
      g.aberturaAtual += (alvoPorta - g.aberturaAtual) * Math.min(1, dt * 3)
      g.porta.rotation.y = -1.25 * g.aberturaAtual

      const frio = temp === undefined || parado ? 0 : Math.min(1, Math.max(0, (10 - temp) / 7))
      this.moverParticulas(g.nevoa, dt * 0.15, (0.15 + 0.6 * frio) * (0.25 + 0.75 * g.aberturaAtual))
      this.moverParticulas(g.nevoaSaida, dt * 0.5, 0.55 * g.aberturaAtual * frio, -1)

      if (g.ventoinha) {
        if (resfr && !parado) g.ventoinha.rotation.y += dt * 18
        this.moverParticulas(g.ventoinhaAr!, dt * 0.8, resfr && !parado ? 0.7 : 0, -1)
      }
      if (g.compressorCorpo && g.compressorBase) {
        const vib = (comp?.vibracao as number | undefined) ?? 0
        const operando = comp?.estado === 'operando' && !parado
        const amp = operando ? Math.min(0.07, Math.max(0, (vib - 1.2) / 60)) + 0.002 : 0
        g.compressorCorpo.position.set(
          g.compressorBase.x + (Math.random() - 0.5) * amp,
          g.compressorBase.y + (Math.random() - 0.5) * amp * 0.5,
          g.compressorBase.z + (Math.random() - 0.5) * amp,
        )
        g.compressorCorpo.rotation.y = operando ? Math.sin(t * 40) * amp * 2 : 0
      }
      if (g.alarmeMesh && g.alarmeLuz) {
        const pisca = alarme && !parado ? (Math.sin(t * 10) > 0 ? 1 : 0.15) : 0
        ;(g.alarmeMesh.material as THREE.MeshStandardMaterial).emissive.setRGB(pisca, 0, 0)
        g.alarmeLuz.intensity = pisca * 4
      }
    }

    this.controles.update()
    this.renderer.render(this.cena, this.camera)
  }

  private moverParticulas(p: THREE.Points, vel: number, opacidade: number, direcao = 1) {
    const mat = p.material as THREE.PointsMaterial
    mat.opacity += (opacidade - mat.opacity) * 0.1
    if (mat.opacity < 0.01) return
    const pos = p.geometry.getAttribute('position') as THREE.BufferAttribute
    const { centro, caixa } = p.userData as { centro: Vec3; caixa: Vec3 }
    for (let i = 0; i < pos.count; i++) {
      let y = pos.getY(i) + vel * direcao * (0.5 + (i % 5) / 5)
      if (y > centro[1] + caixa[1] / 2) y = centro[1] - caixa[1] / 2
      if (y < centro[1] - caixa[1] / 2) y = centro[1] + caixa[1] / 2
      pos.setY(i, y)
    }
    pos.needsUpdate = true
  }

  // ------------------------------------------------------------------ interacao
  private clique(e: PointerEvent) {
    if (Math.hypot(e.clientX - this.inicioToque.x, e.clientY - this.inicioToque.y) > 6) return
    const r = this.renderer.domElement.getBoundingClientRect()
    const ponto = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
    this.raio.setFromCamera(ponto, this.camera)
    const hit = this.raio.intersectObjects(this.clicaveis, false)[0]
    this.selecionado = (hit?.object.userData.id as string | undefined) ?? null
    this.ultimoStatus = 0
    this.aoSelecionar(this.selecionado)
  }

  focar(id: string) {
    const item = this.itens.get(id)
    if (!item) return
    const p = new THREE.Vector3()
    item.indicadores[0].getWorldPosition(p)
    this.controles.target.copy(p)
    this.camera.position.set(p.x + 2.5, p.y + 3, p.z + 5)
  }

  private redimensionar() {
    const w = this.alvo.clientWidth || 800
    const h = this.alvo.clientHeight || 500
    this.renderer.setSize(w, h)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
  }

  destruir() {
    cancelAnimationFrame(this.raf)
    this.observador.disconnect()
    this.controles.dispose()
    this.renderer.dispose()
    this.renderer.domElement.remove()
  }
}

export { somar }
