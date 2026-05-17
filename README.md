# AdaptIQ 🎓

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/sarojsenn/AdaptIQ)](https://github.com/sarojsenn/AdaptIQ/stargazers)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

**Hack-A-Thon: AI For Education**  
Organized by Unstop

**Team:** Bruteforce Army 💪

**Contributors:** 
- [Saroj Sen](https://github.com/sarojsenn) - Team Lead & ML Engineer & Backend Developer
- [Tiyasa Saha](https://github.com/tiyasa-2005) - Frontend Developer & UX Designer  
- [Soumava Das](https://github.com/Cyberdude441) - PPT design & Research

---

## 🚀 Overview

AdaptIQ is a revolutionary AI-powered adaptive assessment platform that transforms the way students learn and assess their knowledge. Built with cutting-edge psychometric models and machine learning algorithms, AdaptIQ delivers personalized, real-time assessments that adapt to each student's unique learning pace and ability level.

### 🎯 Key Highlights
- **🧠 AI-Driven Personalization:** Questions dynamically adjust based on student performance
- **📊 Advanced Analytics:** Real-time insights into learning patterns and skill gaps
- **🎮 Gamified Learning:** Engaging interface that makes assessment fun and interactive
- **🚀 Lightning Fast:** Optimized performance with sub-second response times
- **📱 Cross-Platform:** Works seamlessly across desktop, tablet, and mobile devices

### 📋 Current Status
> **Latest Update (October 2025):** Major enhancements to the adaptive assessment system! The model has been significantly improved with:
> - **Enhanced Question Selection Logic:** Advanced pattern recognition for students struggling with consecutive wrong answers
> - **Clean Dataset:** Fixed 93 placeholder questions with quality mathematical content across Number System and Progressions topics  
> - **Improved Adaptivity:** More sophisticated difficulty adjustment algorithms that better support struggling students
> - **Performance by Topics:** Updated analytics to show performance breakdown by subject areas rather than just difficulty levels
> - **1,539 Total Questions:** Comprehensive dataset covering 9 major topic areas with proper difficulty distribution

### 🆕 Recent Enhancements (October 2025)
- **🔍 Advanced Struggle Detection:** AI now identifies when students are repeatedly answering incorrectly and adjusts strategy accordingly
- **📊 Smarter Question Selection:** Algorithm prioritizes confidence-building questions for struggling students while maintaining challenge for advanced learners  
- **✨ Enhanced User Experience:** Updated charts and visualizations to show "Performance by Topics" for better learning insights
- **🎯 Targeted Support:** New API endpoints provide struggle-specific feedback and personalized learning recommendations
- **📈 Improved Model Training:** Retrained adaptive assessment model with placeholder-free, high-quality mathematical content

---

## ✨ Core Features

### 🧩 Adaptive Assessment Engine
- **Dynamic Question Selection:** AI algorithms select optimal questions based on current ability estimation
- **Real-time Difficulty Adjustment:** Questions automatically adapt to student performance in real-time
- **Multi-subject Support:** Comprehensive coverage across Mathematics, Logic, Verbal Reasoning, and more
- **🆕 Struggle Pattern Recognition:** Advanced detection of consecutive wrong answers with adaptive intervention strategies
- **🆕 Confidence Building Mode:** Automatically switches to easier questions when students need support and encouragement

### 🔬 Advanced Psychometric Models
- **Item Response Theory (IRT):** Implements 2-Parameter Logistic (2PL) model for precise ability estimation
- **Bayesian Knowledge Tracing (BKT):** Tracks knowledge mastery over time with probabilistic modeling  
- **Information-Theoretic Question Selection:** Maximizes learning efficiency through optimal question sequencing

### 📊 Intelligent Analytics & Insights
- **Performance Visualization:** Interactive charts showing progress trends and skill development
- **Competency Mapping:** Detailed breakdown of strengths and areas for improvement
- **Personalized Recommendations:** AI-generated study suggestions based on performance patterns
- **Historical Progress Tracking:** Long-term learning analytics with trend analysis

### 🎨 Modern User Experience  
- **Glass-morphism UI:** Beautiful, modern interface with smooth animations and transitions
- **Responsive Design:** Seamlessly adapts to all screen sizes and devices
- **Accessibility First:** Built with WCAG guidelines for inclusive learning
- **Dark/Light Theme:** Customizable interface preferences

### ⚡ Technical Excellence
- **High-Performance API:** Sub-100ms response times with efficient caching
- **Enterprise Security:** JWT authentication, data encryption, and secure session management
- **Scalable Architecture:** Microservices-ready design for horizontal scaling
- **Real-time Updates:** WebSocket integration for live progress updates

---

## 🏗️ Technology Stack

### Frontend Architecture
```
🎨 UI Framework: HTML5, CSS3, Vanilla JavaScript
🎭 Styling: Tailwind CSS with custom components  
📱 Responsive: Mobile-first design principles
✨ Effects: Glass-morphism, smooth animations, micro-interactions
🎯 Performance: Optimized loading, lazy loading, code splitting
```

### Backend Infrastructure  
```
🐍 Python: Flask-based adaptive engine with scikit-learn
🟢 Node.js: Express.js API server with high concurrency
🔐 Authentication: JWT tokens with bcrypt password hashing
📧 Communication: Nodemailer integration for notifications
🔄 Real-time: WebSocket support for live updates
```

### Machine Learning Pipeline
```
🧠 IRT Models: 2PL Item Response Theory implementation
📈 BKT: Bayesian Knowledge Tracing algorithms  
🎯 Question Selection: Information gain optimization
📊 Analytics: Real-time performance modeling
🔄 Model Training: Automated retraining pipeline
```

### Database & Storage
```
🗄️ Database: MongoDB with Mongoose ODM
📁 File Storage: Local storage with cloud-ready architecture
🔍 Indexing: Optimized queries with compound indexes
💾 Caching: In-memory caching for frequently accessed data
```

### DevOps & Deployment
```
🐳 Containerization: Docker-ready configuration
☁️ Cloud Ready: AWS/Azure deployment compatible  
🔄 Version Control: Git with branching strategies
📦 Package Management: npm/pip with lock files
```

---

## � Student Experience

### 📊 Interactive Dashboard
- **Performance Overview:** Real-time visualization of learning progress and achievements
- **Skill Radar Chart:** Multi-dimensional view of competency across different subjects  
- **Progress Timeline:** Historical view of learning journey with milestone tracking
- **Accuracy Trends:** Dynamic charts showing improvement patterns over time

### 🎮 Assessment Interface
- **Adaptive Questions:** Seamlessly transitioning difficulty levels based on performance
- **Multiple Question Types:** MCQs, numerical inputs, drag-and-drop, and more
- **Instant Feedback:** Immediate explanations and hints for incorrect answers
- **Progress Indicators:** Visual cues showing current position in assessment

### 🏆 Gamification Elements  
- **Achievement System:** Unlock badges and rewards for consistent performance
- **Streak Tracking:** Maintain learning streaks with daily assessment goals
- **Leaderboards:** Compare progress with peers (optional and anonymous)
- **Skill Trees:** Visual progression paths for different subject areas

### 🎨 Personalization Options
- **Custom Themes:** Multiple color schemes and interface preferences
- **Accessibility Features:** Font size adjustment, high contrast mode, screen reader support
- **Learning Preferences:** Visual, auditory, or kinesthetic learning mode adaptations
- **Goal Setting:** Personal targets and milestone configuration

---

## ⚡ Quick Start Guide

### 📋 Prerequisites
- **Node.js** (v16 or higher) - [Download here](https://nodejs.org/)
- **Python** (v3.8 or higher) - [Download here](https://python.org/)
- **Git** - [Download here](https://git-scm.com/)

### 🚀 Installation Steps

1. **Clone the repository:**
```bash
git clone https://github.com/sarojsenn/AdaptIQ.git
cd AdaptIQ
```

2. **Set up the backend environment:**
```bash
# Install Node.js dependencies
npm install

# Install Python dependencies (if using Python ML models)
pip install flask scikit-learn numpy pandas matplotlib seaborn
```

3. **Configure environment variables:**
```bash
# Create .env file
cp .env.example .env

# Edit .env with your configuration
# Add your MongoDB URI, JWT secret, email credentials, etc.
```

4. **Start the services:**
```bash
# Start the Node.js API server
npm start

# In a new terminal, start the Python ML service
python adaptive_api_server.py
```

5. **Launch the application:**
```bash
# Option 1: Use live server extension in VS Code
# Open client/pages/LandingPage.html

# Option 2: Use Python's built-in server
cd client
python -m http.server 3000
# Navigate to http://localhost:3000/pages/LandingPage.html
```

### 🎯 First Run
1. Open your browser and navigate to the landing page
2. Create a new student account via the registration page  
3. Verify your email (check spam folder if needed)
4. Log in and start your first adaptive assessment!

### 🔧 Development Setup
```bash
# For development with auto-reload
npm run dev

# For frontend development
cd client
npm install
npm run dev
```

---

## 📁 Project Structure
```
AdaptIQ/
├── 📂 client/                    # Frontend application
│   ├── 📂 assets/               # Images, icons, and media files
│   ├── 📂 css/                  # Stylesheets and Tailwind config
│   ├── 📂 pages/                # HTML pages and components
│   └── � package.json          # Frontend dependencies
├── 📂 data/                     # Assessment datasets and questions
│   ├── 📂 Geometry/             # Subject-specific question banks
│   └── 📂 student_history/      # User performance data
├── 📂 utils/                    # Utility functions and helpers
├── 📄 server.js                 # Node.js API server
├── 📄 adaptive_api_server.py    # Python ML service
├── 📄 train_adaptive_model.py   # Model training scripts
└── 📄 package.json              # Backend dependencies
```

## 🔮 Future Roadmap

### 🎯 Phase 1: Enhanced Accessibility (Q1 2024)
- **🧠 Dyslexia Support**
  - Text-to-speech integration with natural voice synthesis
  - Dyslexia-friendly fonts (OpenDyslexic, Comic Sans options)  
  - Color overlay filters and high contrast modes
  - Reading speed adjustment and pause controls

- **♿ Universal Accessibility**
  - Full screen reader compatibility (NVDA, JAWS, VoiceOver)
  - Keyboard-only navigation with focus indicators
  - Audio-based assessment modes for visually impaired users
  - Customizable UI scaling (up to 200% zoom)

### 🎯 Phase 2: Advanced Intelligence (Q2 2024) 
- **🔬 Enhanced ML Models**
  - Upgrade from 2PL to 4PL Item Response Theory
  - Multi-dimensional IRT for complex skill assessment
  - Deep learning integration for question generation
  - Emotional AI for stress and engagement detection

- **🌐 Content Expansion**
  - 15+ subjects including Sciences, Languages, Arts
  - Grade-level adaptation (K-12, undergraduate, professional)
  - Multi-language support (Spanish, French, Mandarin, Hindi)
  - Cultural adaptation for regional education systems

### 🎯 Phase 3: Ecosystem Integration (Q3 2024)
- **👩‍🏫 Educator Platform**
  - Comprehensive teacher dashboard and analytics
  - Classroom management and student progress monitoring
  - Custom assessment creation tools
  - Parent/guardian progress reporting

- **🏫 Enterprise Features**
  - Learning Management System (LMS) integration
  - Single Sign-On (SSO) with popular platforms
  - Advanced analytics and reporting API
  - White-label solutions for educational institutions

### � Phase 4: Scale & Innovation (Q4 2024)
- **☁️ Cloud Infrastructure**
  - Microservices architecture with Docker/Kubernetes
  - Global CDN for sub-50ms response times worldwide
  - Auto-scaling capabilities for millions of concurrent users
  - Advanced security with SOC 2 Type II compliance

- **🤖 AI-Powered Innovations**
  - Personalized learning path recommendations
  - Automated content generation and question creation
  - Predictive analytics for learning outcome forecasting
  - Integration with emerging technologies (AR/VR, voice interfaces)

## 🤝 Contributing

We welcome contributions from the community! Here's how you can help:

### 🐛 Bug Reports
- Use GitHub Issues to report bugs
- Include detailed reproduction steps
- Provide system information and screenshots

### 💡 Feature Requests  
- Discuss new ideas in GitHub Discussions
- Follow the feature request template
- Consider implementation feasibility

### � Development
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and test thoroughly
4. Commit with clear messages: `git commit -m 'Add amazing feature'`
5. Push to your branch: `git push origin feature/amazing-feature`
6. Open a Pull Request with detailed description

### 📋 Development Guidelines
- Follow existing code style and conventions
- Add tests for new functionality
- Update documentation as needed
- Ensure all tests pass before submitting PR

## 📞 Support & Contact

- **📧 Email:** [sarojsenofficial@gmail.com](mailto:sarojsenofficial@gmail.com)
- **💬 GitHub Issues:** [Report Issues](https://github.com/sarojsenn/AdaptIQ/issues)
- **📖 Documentation:** [Wiki](https://github.com/sarojsenn/AdaptIQ/wiki)
- **💭 Discussions:** [GitHub Discussions](https://github.com/sarojsenn/AdaptIQ/discussions)

## 🏆 Acknowledgments

- **Unstop Team** for organizing the AI in Education hackathon
- **Open Source Community** for the amazing tools and libraries
- **Educational Psychology Research** for IRT and BKT methodologies
- **Beta Testers** who provided valuable feedback during development

## 📊 Project Stats

![GitHub repo size](https://img.shields.io/github/repo-size/sarojsenn/AdaptIQ)
![GitHub code size in bytes](https://img.shields.io/github/languages/code-size/sarojsenn/AdaptIQ)
![GitHub top language](https://img.shields.io/github/languages/top/sarojsenn/AdaptIQ)
![GitHub last commit](https://img.shields.io/github/last-commit/sarojsenn/AdaptIQ)

---

## �📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

### 🔓 What this means:
- ✅ Commercial use allowed
- ✅ Modification allowed  
- ✅ Distribution allowed
- ✅ Private use allowed
- ❗ License and copyright notice required

---

<div align="center">

**Made with ❤️ by Team Bruteforce Army**

*Transforming Education Through Intelligent Assessment*

[⭐ Star this repo](https://github.com/sarojsenn/AdaptIQ/stargazers) | [🐛 Report Bug](https://github.com/sarojsenn/AdaptIQ/issues) | [💡 Request Feature](https://github.com/sarojsenn/AdaptIQ/issues)

</div>
#   A d a p t I Q  
 