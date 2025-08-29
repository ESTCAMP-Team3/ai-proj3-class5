#!/bin/bash
# 졸음운전 방지 시스템 - 자동 설치 스크립트

set -e  # 에러 발생시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 로고 출력
echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║                                                      ║"
echo "║  🚗 졸음운전 방지 시스템 자동 설치 스크립트          ║"  
echo "║     No Drowsy!! - AI Powered Safety System          ║"
echo "║                                                      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 함수 정의
print_step() {
    echo -e "${BLUE}[단계 $1]${NC} $2"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# OS 확인
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        DISTRO=$(lsb_release -si 2>/dev/null || echo "Unknown")
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        OS="windows"
    else
        OS="unknown"
    fi
    
    print_success "운영체제 감지: $OS"
}

# Python 버전 확인
check_python() {
    print_step "1" "Python 설치 확인"
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        print_error "Python이 설치되어 있지 않습니다."
        echo "Python 3.8+ 를 설치한 후 다시 실행해주세요."
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON_CMD --version | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
    
    if [[ $PYTHON_MAJOR -lt 3 || ($PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 8) ]]; then
        print_error "Python 3.8+ 가 필요합니다. 현재 버전: $PYTHON_VERSION"
        exit 1
    fi
    
    print_success "Python $PYTHON_VERSION 확인됨"
}

# 가상환경 생성
create_venv() {
    print_step "2" "가상환경 설정"
    
    if [[ ! -d "venv" ]]; then
        print_success "가상환경 생성 중..."
        $PYTHON_CMD -m venv venv
    else
        print_success "기존 가상환경 발견"
    fi
    
    # 가상환경 활성화
    if [[ "$OS" == "windows" ]]; then
        source venv/Scripts/activate
    else
        source venv/bin/activate
    fi
    
    print_success "가상환경 활성화됨"
}

# 패키지 설치
install_packages() {
    print_step "3" "Python 패키지 설치"
    
    # pip 업그레이드
    python -m pip install --upgrade pip
    
    # 요구사항 설치
    if [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt
        print_success "패키지 설치 완료"
    else
        print_error "requirements.txt 파일을 찾을 수 없습니다."
        exit 1
    fi
}

# 환경변수 파일 생성
setup_env() {
    print_step "4" "환경변수 설정"
    
    if [[ ! -f ".env" ]]; then
        if [[ -f ".env.example" ]]; then
            cp .env.example .env
            print_success ".env 파일 생성됨"
            print_warning ".env 파일을 편집하여 실제 설정값을 입력하세요"
        else
            print_warning ".env.example 파일이 없습니다. 수동으로 .env 파일을 생성하세요."
        fi
    else
        print_success ".env 파일이 이미 존재합니다"
    fi
}

# 필수 디렉토리 생성
create_directories() {
    print_step "5" "필수 디렉토리 생성"
    
    directories=("static/sounds" "logs" "uploads" "tests")
    
    for dir in "${directories[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            print_success "$dir 디렉토리 생성"
        fi
    done
}

# 권한 설정 (Unix 계열만)
set_permissions() {
    if [[ "$OS" != "windows" ]]; then
        print_step "6" "권한 설정"
        
        # 실행 권한 설정
        chmod +x scripts/*.sh 2>/dev/null || true
        chmod +x *.py 2>/dev/null || true
        
        print_success "실행 권한 설정 완료"
    fi
}

# 테스트 실행
run_tests() {
    print_step "7" "기본 테스트 실행"
    
    if [[ -f "tests/test_basic.py" ]]; then
        python tests/test_basic.py
        print_success "기본 테스트 통과"
    else
        print_warning "테스트 파일을 찾을 수 없습니다"
    fi
}

# Docker 설치 확인 (선택사항)
check_docker() {
    print_step "8" "Docker 확인 (선택사항)"
    
    if command -v docker &> /dev/null; then
        print_success "Docker가 설치되어 있습니다"
        print_success "컨테이너 실행: docker-compose up -d"
    else
        print_warning "Docker가 설치되어 있지 않습니다 (선택사항)"
    fi
}

# 설치 완료 메시지
installation_complete() {
    echo
    echo -e "${GREEN}╔══════════════════════════════════════════════════════╗"
    echo -e "║                                                      ║"
    echo -e "║  🎉 설치가 완료되었습니다!                           ║"
    echo -e "║                                                      ║"
    echo -e "╚══════════════════════════════════════════════════════╝${NC}"
    echo
    echo -e "${BLUE}다음 단계:${NC}"
    echo -e "1. .env 파일을 편집하여 API 키 등을 설정하세요"
    echo -e "2. 서버 실행: ${YELLOW}python run.py${NC}"
    echo -e "3. 브라우저에서 ${YELLOW}http://localhost:8000${NC} 접속"
    echo -e "4. D-score 시뮬레이터: ${YELLOW}python d_writer.py${NC}"
    echo
    echo -e "${BLUE}도움말:${NC}"
    echo -e "- 문서: README.md"
    echo -e "- 이슈 리포트: GitHub Issues"
    echo -e "- 테스트: python -m pytest tests/ -v"
}

# 메인 실행 함수
main() {
    echo "설치를 시작합니다..."
    echo
    
    detect_os
    check_python
    create_venv
    install_packages
    setup_env
    create_directories
    set_permissions
    run_tests
    check_docker
    
    installation_complete
}

# 도움말 표시
show_help() {
    echo "사용법: $0 [옵션]"
    echo
    echo "옵션:"
    echo "  -h, --help     이 도움말 표시"
    echo "  --skip-tests   테스트 건너뛰기"
    echo "  --docker-only  Docker만 설치"
    echo
    echo "예시:"
    echo "  $0                # 전체 설치"
    echo "  $0 --skip-tests   # 테스트 없이 설치"
}

# 명령행 인수 처리
case "${1:-}" in
    -h|--help)
        show_help
        exit 0
        ;;
    --skip-tests)
        SKIP_TESTS=true
        ;;
    --docker-only)
        DOCKER_ONLY=true
        ;;
esac

# 스크립트 실행
if [[ "${DOCKER_ONLY:-}" == "true" ]]; then
    check_docker
else
    main
fi