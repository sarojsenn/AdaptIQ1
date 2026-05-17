const express = require('express');
const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const nodemailer = require('nodemailer');
const crypto = require('crypto');
const cors = require('cors');
const path = require('path');
require('dotenv').config();

const app = express();

// Middleware
app.use(cors({
    origin: ['http://localhost:3000', 'http://127.0.0.1:3000', 'null'],
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization']
}));
app.use(express.json());
app.use(express.static('client'));

// Content Security Policy
app.use((req, res, next) => {
    // Allow connections to API on 3000 (this server) and 5000 (adaptive API)
    res.setHeader(
        "Content-Security-Policy",
        "default-src 'self'; connect-src 'self' http://localhost:3000 http://localhost:5000"
    );
    next();
});

// Request logging middleware
app.use((req, res, next) => {
    console.log(`📥 ${req.method} ${req.path} - ${new Date().toISOString()}`);
    if (req.body && Object.keys(req.body).length > 0) {
        console.log('📄 Request body:', { ...req.body, password: req.body.password ? '***' : undefined });
    }
    next();
});

// MongoDB Connection
mongoose.connect(process.env.MONGODB_URI, {
    useNewUrlParser: true,
    useUnifiedTopology: true
}).then(() => {
    console.log('Connected to MongoDB');
}).catch(err => {
    console.error('MongoDB connection error:', err);
});

// User Schema
const userSchema = new mongoose.Schema({
    firstName: { type: String, required: true },
    lastName: { type: String, required: true },
    email: { type: String, required: true, unique: true },
    password: { type: String, required: true },
    isVerified: { type: Boolean, default: false },
    otp: { type: String },
    otpExpires: { type: Date },
    createdAt: { type: Date, default: Date.now }
});

const User = mongoose.model('User', userSchema);

// Assessment Session Schema
const sessionSchema = new mongoose.Schema({
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
    ability: { type: Number, default: 0 },
    questionsAnswered: { type: Number, default: 0 },
    correctAnswers: { type: Number, default: 0 },
    assessmentHistory: [{
        questionId: Number,
        difficulty: Number,
        correct: Boolean,
        timestamp: { type: Date, default: Date.now }
    }],
    lastActivity: { type: Date, default: Date.now }
});

const Session = mongoose.model('Session', sessionSchema);

// Email Transporter
const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: {
        user: process.env.EMAIL_USER,
        pass: process.env.EMAIL_PASS
    }
});

// Generate OTP
function generateOTP() {
    return Math.floor(100000 + Math.random() * 900000).toString();
}

// Validate JWT Secret
if (!process.env.JWT_SECRET) {
    console.error('❌ JWT_SECRET is required in environment variables');
    process.exit(1);
}

if (process.env.JWT_SECRET.length < 32) {
    console.warn('⚠️  Warning: JWT_SECRET should be at least 32 characters long for security');
} else {
    console.log('✅ JWT Secret is properly configured');
}

// Send OTP Email
async function sendOTPEmail(email, otp, firstName) {
    try {
        const mailOptions = {
            from: process.env.EMAIL_USER,
            to: email,
            subject: 'AdaptIQ - Email Verification',
            html: `
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; font-family: Arial, sans-serif;">
                    <div style="background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                        <h1 style="color: white; margin: 0; font-size: 28px;">🎓 AdaptIQ</h1>
                        <p style="color: white; margin: 10px 0 0; font-size: 16px;">Adaptive Learning Platform</p>
                    </div>
                    <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                        <h2 style="color: #333; margin-bottom: 20px;">Welcome ${firstName}!</h2>
                        <p style="color: #666; font-size: 16px; line-height: 1.6;">
                            Thank you for joining AdaptIQ! Please verify your email address to complete your registration.
                        </p>
                        <div style="background: white; padding: 20px; margin: 20px 0; border-radius: 8px; text-align: center; border: 2px dashed #8b5cf6;">
                            <p style="color: #333; margin: 0 0 10px; font-size: 14px;">Your verification code is:</p>
                            <h1 style="color: #8b5cf6; margin: 0; font-size: 36px; letter-spacing: 8px;">${otp}</h1>
                            <p style="color: #666; margin: 10px 0 0; font-size: 12px;">This code will expire in 10 minutes</p>
                        </div>
                        <p style="color: #666; font-size: 14px; line-height: 1.6;">
                            If you didn't create an account with AdaptIQ, please ignore this email.
                        </p>
                        <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center;">
                            <p style="color: #999; font-size: 12px; margin: 0;">
                                © 2025 AdaptIQ. All rights reserved.
                            </p>
                        </div>
                    </div>
                </div>
            `
        };

        console.log(`Sending OTP email to ${email}...`);
        const result = await transporter.sendMail(mailOptions);
        console.log(`OTP email sent successfully to ${email}`);
        return result;
    } catch (error) {
        console.error('Error sending OTP email:', error);
        throw new Error('Failed to send verification email. Please try again.');
    }
}

// Test email configuration on startup
async function testEmailConfiguration() {
    try {
        await transporter.verify();
        console.log('✅ Email configuration is valid');
    } catch (error) {
        console.error('❌ Email configuration error:', error.message);
        console.log('Please check your EMAIL_USER and EMAIL_PASS in .env file');
    }
}

// Routes

// Serve HTML pages
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'client', 'pages', 'LandingPage.html'));
});

app.get('/signup', (req, res) => {
    res.sendFile(path.join(__dirname, 'client', 'pages', 'Registration.html'));
});

app.get('/signin', (req, res) => {
    res.sendFile(path.join(__dirname, 'client', 'pages', 'SignIn.html'));
});

app.get('/dashboard', (req, res) => {
    res.sendFile(path.join(__dirname, 'client', 'pages', 'StudentDashboard.html'));
});

app.get('/verify', (req, res) => {
    res.sendFile(path.join(__dirname, 'client', 'pages', 'VerifyEmail.html'));
});

// Registration Route
app.post('/api/register', async (req, res) => {
    try {
        console.log('📝 Registration request received:', req.body);
        console.log('📋 Request headers:', req.headers);
        console.log('📄 Content-Type:', req.get('Content-Type'));
        
        const { firstName, lastName, email, password } = req.body;

        if (!firstName || !lastName || !email || !password) {
            console.log('❌ Missing required fields:', { firstName: !!firstName, lastName: !!lastName, email: !!email, password: !!password });
            return res.status(400).json({
                success: false,
                message: 'All fields are required'
            });
        }

        console.log('🔍 Checking for existing user:', email);
        // Check if user already exists
        const existingUser = await User.findOne({ email }).maxTimeMS(5000);
        console.log('📋 Existing user check result:', existingUser ? 'User found' : 'No user found');
        
        if (existingUser) {
            console.log('❌ User already exists');
            return res.status(400).json({ 
                success: false, 
                message: 'User already exists with this email' 
            });
        }

        // Hash password
        console.log('🔐 Hashing password...');
        const hashedPassword = await bcrypt.hash(password, 12);

        // Generate OTP
        console.log('🔢 Generating OTP...');
        const otp = generateOTP();
        const otpExpires = new Date(Date.now() + 10 * 60 * 1000); // 10 minutes

        // Create user
        console.log('👤 Creating new user...');
        const user = new User({
            firstName,
            lastName,
            email,
            password: hashedPassword,
            otp,
            otpExpires
        });

        console.log('💾 Saving user to database...');
        await user.save();
        console.log('✅ User created successfully:', user._id);

        // Send OTP email
        try {
            console.log('📧 Sending OTP email to:', email);
            await sendOTPEmail(email, otp, firstName);
            console.log('✅ OTP email sent successfully');
            
            res.status(201).json({
                success: true,
                message: 'Registration successful! Please check your email for verification code.',
                userId: user._id
            });
        } catch (emailError) {
            // If email sending fails, still allow registration but inform user
            console.error('Email sending failed:', emailError);
            
            res.status(201).json({
                success: true,
                message: 'Registration successful! However, there was an issue sending the verification email. Please try resending the verification code.',
                userId: user._id,
                emailError: true
            });
        }
    } catch (error) {
        console.error('❌ Registration error:', error);
        console.error('Error details:', error.message);
        console.error('Stack trace:', error.stack);
        res.status(500).json({
            success: false,
            message: 'Registration failed. Please try again.',
            error: process.env.NODE_ENV === 'development' ? error.message : undefined
        });
    }
});

// Verify OTP Route
app.post('/api/verify-otp', async (req, res) => {
    try {
        const { userId, otp } = req.body;

        const user = await User.findById(userId);
        if (!user) {
            return res.status(404).json({
                success: false,
                message: 'User not found'
            });
        }

        if (user.otp !== otp || user.otpExpires < new Date()) {
            return res.status(400).json({
                success: false,
                message: 'Invalid or expired OTP'
            });
        }

        // Verify user
        user.isVerified = true;
        user.otp = undefined;
        user.otpExpires = undefined;
        await user.save();

        // Create session
        const session = new Session({ userId: user._id });
        await session.save();

        // Generate JWT token
        const token = jwt.sign(
            { userId: user._id, email: user.email },
            process.env.JWT_SECRET,
            { expiresIn: '7d' }
        );

        res.json({
            success: true,
            message: 'Email verified successfully!',
            token,
            user: {
                id: user._id,
                firstName: user.firstName,
                lastName: user.lastName,
                email: user.email
            }
        });
    } catch (error) {
        console.error('OTP verification error:', error);
        res.status(500).json({
            success: false,
            message: 'Verification failed. Please try again.'
        });
    }
});

// Resend OTP Route
app.post('/api/resend-otp', async (req, res) => {
    try {
        const { userId } = req.body;

        const user = await User.findById(userId);
        if (!user) {
            return res.status(404).json({
                success: false,
                message: 'User not found'
            });
        }

        if (user.isVerified) {
            return res.status(400).json({
                success: false,
                message: 'User is already verified'
            });
        }

        // Generate new OTP
        const otp = generateOTP();
        const otpExpires = new Date(Date.now() + 10 * 60 * 1000);

        user.otp = otp;
        user.otpExpires = otpExpires;
        await user.save();

        // Send OTP email
        await sendOTPEmail(user.email, otp, user.firstName);

        res.json({
            success: true,
            message: 'New verification code sent to your email'
        });
    } catch (error) {
        console.error('Resend OTP error:', error);
        res.status(500).json({
            success: false,
            message: 'Failed to resend verification code'
        });
    }
});

// Login Route
app.post('/api/login', async (req, res) => {
    try {
        const { email, password } = req.body;

        // Find user
        const user = await User.findOne({ email });
        if (!user) {
            return res.status(400).json({
                success: false,
                message: 'Invalid email or password'
            });
        }

        // Check password
        const isValidPassword = await bcrypt.compare(password, user.password);
        if (!isValidPassword) {
            return res.status(400).json({
                success: false,
                message: 'Invalid email or password'
            });
        }

        // Check if verified
        if (!user.isVerified) {
            // Generate new OTP for unverified user
            const otp = generateOTP();
            const otpExpires = new Date(Date.now() + 10 * 60 * 1000);

            user.otp = otp;
            user.otpExpires = otpExpires;
            await user.save();

            // Send new OTP
            try {
                await sendOTPEmail(user.email, otp, user.firstName);
            } catch (emailError) {
                console.error('Failed to send OTP email:', emailError);
            }

            return res.status(200).json({
                success: true,
                message: 'Please verify your email first. A new verification code has been sent.',
                requiresVerification: true,
                userId: user._id
            });
        }

        // Generate JWT token
        const token = jwt.sign(
            { userId: user._id, email: user.email },
            process.env.JWT_SECRET,
            { expiresIn: '7d' }
        );

        // Update or create session
        let session = await Session.findOne({ userId: user._id });
        if (!session) {
            session = new Session({ userId: user._id });
        }
        session.lastActivity = new Date();
        await session.save();

        res.json({
            success: true,
            message: 'Login successful!',
            token,
            user: {
                id: user._id,
                firstName: user.firstName,
                lastName: user.lastName,
                email: user.email
            }
        });
    } catch (error) {
        console.error('Login error:', error);
        res.status(500).json({
            success: false,
            message: 'Login failed. Please try again.'
        });
    }
});

// Middleware to verify JWT token
const verifyToken = (req, res, next) => {
    const token = req.header('Authorization')?.replace('Bearer ', '');
    
    if (!token) {
        return res.status(401).json({
            success: false,
            message: 'Access denied. No token provided.'
        });
    }

    try {
        const decoded = jwt.verify(token, process.env.JWT_SECRET);
        req.user = decoded;
        next();
    } catch (error) {
        res.status(400).json({
            success: false,
            message: 'Invalid token'
        });
    }
};

// Get user profile
app.get('/api/profile', verifyToken, async (req, res) => {
    try {
        const user = await User.findById(req.user.userId).select('-password -otp -otpExpires');
        const session = await Session.findOne({ userId: req.user.userId });

        res.json({
            success: true,
            user,
            session: session || { ability: 0, questionsAnswered: 0, correctAnswers: 0 }
        });
    } catch (error) {
        console.error('Profile fetch error:', error);
        res.status(500).json({
            success: false,
            message: 'Failed to fetch profile'
        });
    }
});

// Logout route
app.post('/api/logout', verifyToken, (req, res) => {
    res.json({
        success: true,
        message: 'Logged out successfully'
    });
});

// Forgot Password Route
app.post('/api/forgot-password', async (req, res) => {
    try {
        const { email } = req.body;

        if (!email) {
            return res.status(400).json({
                success: false,
                message: 'Email is required'
            });
        }

        // Find user by email
        const user = await User.findOne({ email });
        if (!user) {
            // For security, don't reveal if email exists or not
            return res.status(200).json({
                success: true,
                message: 'If this email exists, a reset code has been sent.',
                userId: 'dummy' // Don't expose real user data
            });
        }

        // Generate reset OTP
        const resetOtp = generateOTP();
        const resetOtpExpires = new Date(Date.now() + 10 * 60 * 1000); // 10 minutes

        user.otp = resetOtp;
        user.otpExpires = resetOtpExpires;
        await user.save();

        // Send reset email
        try {
            const resetEmailOptions = {
                from: process.env.EMAIL_USER,
                to: email,
                subject: 'AdaptIQ - Password Reset',
                html: `
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; font-family: Arial, sans-serif;">
                        <div style="background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                            <h1 style="color: white; margin: 0; font-size: 28px;">🔐 AdaptIQ</h1>
                            <p style="color: white; margin: 10px 0 0; font-size: 16px;">Password Reset Request</p>
                        </div>
                        <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                            <h2 style="color: #333; margin-bottom: 20px;">Reset Your Password</h2>
                            <p style="color: #666; font-size: 16px; line-height: 1.6;">
                                We received a request to reset your password. Use the code below to set a new password:
                            </p>
                            <div style="background: white; padding: 20px; margin: 20px 0; border-radius: 8px; text-align: center; border: 2px dashed #8b5cf6;">
                                <p style="color: #333; margin: 0 0 10px; font-size: 14px;">Your password reset code:</p>
                                <h1 style="color: #8b5cf6; margin: 0; font-size: 36px; letter-spacing: 8px;">${resetOtp}</h1>
                                <p style="color: #666; margin: 10px 0 0; font-size: 12px;">This code will expire in 10 minutes</p>
                            </div>
                            <p style="color: #666; font-size: 14px; line-height: 1.6;">
                                If you didn't request a password reset, please ignore this email. Your password will remain unchanged.
                            </p>
                            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center;">
                                <p style="color: #999; font-size: 12px; margin: 0;">
                                    © 2025 AdaptIQ. All rights reserved.
                                </p>
                            </div>
                        </div>
                    </div>
                `
            };

            await transporter.sendMail(resetEmailOptions);
            console.log(`Password reset email sent to ${email}`);
        } catch (emailError) {
            console.error('Error sending reset email:', emailError);
            return res.status(500).json({
                success: false,
                message: 'Failed to send reset email. Please try again.'
            });
        }

        res.json({
            success: true,
            message: 'If this email exists, a reset code has been sent.',
            userId: user._id
        });
    } catch (error) {
        console.error('Forgot password error:', error);
        res.status(500).json({
            success: false,
            message: 'Failed to process request. Please try again.'
        });
    }
});

// Reset Password Route
app.post('/api/reset-password', async (req, res) => {
    try {
        const { userId, otp, newPassword } = req.body;

        if (!userId || !otp || !newPassword) {
            return res.status(400).json({
                success: false,
                message: 'All fields are required'
            });
        }

        // Find user by ID
        const user = await User.findById(userId);
        if (!user) {
            return res.status(404).json({
                success: false,
                message: 'Invalid reset request'
            });
        }

        // Verify OTP
        if (user.otp !== otp || user.otpExpires < new Date()) {
            return res.status(400).json({
                success: false,
                message: 'Invalid or expired reset code'
            });
        }

        // Hash new password
        const hashedPassword = await bcrypt.hash(newPassword, 12);

        // Update user password and clear OTP
        user.password = hashedPassword;
        user.otp = undefined;
        user.otpExpires = undefined;
        await user.save();

        console.log(`Password successfully reset for user: ${user.email}`);

        res.json({
            success: true,
            message: 'Password reset successfully!'
        });
    } catch (error) {
        console.error('Reset password error:', error);
        res.status(500).json({
            success: false,
            message: 'Failed to reset password. Please try again.'
        });
    }
});

// Dashboard API endpoints
app.get('/api/dashboard/stats', verifyToken, async (req, res) => {
    try {
        const userId = req.user.userId;
        console.log('📊 Fetching dashboard stats for user:', userId);
        
        const session = await Session.findOne({ userId });
        const user = await User.findById(userId);
        
        if (!session) {
            return res.json({
                success: true,
                stats: {
                    totalQuestions: 0,
                    correctAnswers: 0,
                    accuracy: 0,
                    currentAbility: 0,
                    assessmentsTaken: 0,
                    averageScore: 0
                }
            });
        }
        
        const accuracy = session.questionsAnswered > 0 ? 
            Math.round((session.correctAnswers / session.questionsAnswered) * 100) : 0;
        
        const averageScore = session.assessmentHistory.length > 0 ?
            Math.round(session.assessmentHistory.reduce((sum, assessment) => 
                sum + (assessment.correct ? 100 : 0), 0) / session.assessmentHistory.length) : 0;
        
        res.json({
            success: true,
            stats: {
                totalQuestions: session.questionsAnswered,
                correctAnswers: session.correctAnswers,
                accuracy: accuracy,
                currentAbility: Math.round(session.ability * 100) / 100,
                assessmentsTaken: session.assessmentHistory.length,
                averageScore: averageScore
            }
        });
    } catch (error) {
        console.error('Dashboard stats error:', error);
        res.status(500).json({
            success: false,
            message: 'Failed to fetch dashboard stats'
        });
    }
});

app.get('/api/dashboard/progress', verifyToken, async (req, res) => {
    try {
        const userId = req.user.userId;
        console.log('📈 Fetching progress data for user:', userId);
        
        const session = await Session.findOne({ userId });
        
        if (!session || !session.assessmentHistory.length) {
            return res.json({
                success: true,
                progress: {
                    abilityProgress: [],
                    accuracyTrend: [],
                    difficultyDistribution: { easy: 0, moderate: 0, hard: 0, veryHard: 0 },
                    recentPerformance: []
                }
            });
        }
        
        // Calculate ability progress over time
        const abilityProgress = [];
        let runningAbility = 0;
        const historyChunks = Math.ceil(session.assessmentHistory.length / 10);
        
        for (let i = 0; i < session.assessmentHistory.length; i += historyChunks) {
            const chunk = session.assessmentHistory.slice(i, i + historyChunks);
            const correct = chunk.filter(q => q.correct).length;
            runningAbility += (correct / chunk.length - 0.5) * 0.3;
            abilityProgress.push(Math.round(runningAbility * 100) / 100);
        }
        
        // Calculate accuracy trend
        const accuracyTrend = [];
        for (let i = 0; i < session.assessmentHistory.length; i += historyChunks) {
            const chunk = session.assessmentHistory.slice(0, i + historyChunks);
            const accuracy = (chunk.filter(q => q.correct).length / chunk.length) * 100;
            accuracyTrend.push(Math.round(accuracy));
        }
        
        // Calculate difficulty distribution
        const difficultyDistribution = session.assessmentHistory.reduce((dist, assessment) => {
            if (assessment.difficulty <= 0.3) dist.easy++;
            else if (assessment.difficulty <= 0.6) dist.moderate++;
            else if (assessment.difficulty <= 0.8) dist.hard++;
            else dist.veryHard++;
            return dist;
        }, { easy: 0, moderate: 0, hard: 0, veryHard: 0 });
        
        // Get recent performance (last 10 assessments)
        const recentPerformance = session.assessmentHistory
            .slice(-10)
            .map(assessment => ({
                questionId: assessment.questionId,
                difficulty: Math.round(assessment.difficulty * 100),
                correct: assessment.correct,
                timestamp: assessment.timestamp
            }));
        
        res.json({
            success: true,
            progress: {
                abilityProgress,
                accuracyTrend,
                difficultyDistribution,
                recentPerformance
            }
        });
    } catch (error) {
        console.error('Dashboard progress error:', error);
        res.status(500).json({
            success: false,
            message: 'Failed to fetch progress data'
        });
    }
});

// Get recent activity
app.get('/api/dashboard/recent-activity', verifyToken, async (req, res) => {
    try {
        const userId = req.user.userId;
        console.log('📋 Fetching recent activity for user:', userId);
        
        const session = await Session.findOne({ userId });
        
        if (!session || !session.assessmentHistory.length) {
            return res.json({
                success: true,
                activities: []
            });
        }
        
        // Get recent assessment activities (group by time periods)
        const activities = [];
        const recentHistory = session.assessmentHistory.slice(-20); // Last 20 questions
        
        // Group questions by time periods (within 1 hour = same session)
        const sessionGroups = [];
        let currentGroup = [];
        let lastTimestamp = null;
        
        recentHistory.forEach(item => {
            const currentTime = new Date(item.timestamp);
            
            if (!lastTimestamp || (currentTime - lastTimestamp) > 3600000) { // 1 hour gap
                if (currentGroup.length > 0) {
                    sessionGroups.push(currentGroup);
                }
                currentGroup = [item];
            } else {
                currentGroup.push(item);
            }
            lastTimestamp = currentTime;
        });
        
        if (currentGroup.length > 0) {
            sessionGroups.push(currentGroup);
        }
        
        // Create activity entries for each session group
        sessionGroups.reverse().slice(0, 5).forEach((group, index) => {
            const correctAnswers = group.filter(q => q.correct).length;
            const totalQuestions = group.length;
            const accuracy = Math.round((correctAnswers / totalQuestions) * 100);
            const avgDifficulty = group.reduce((sum, q) => sum + q.difficulty, 0) / group.length;
            
            let subject = 'Mixed Topics';
            let icon = '📊';
            let color = 'purple-primary';
            
            // Determine subject based on difficulty patterns or question IDs
            if (avgDifficulty < 0.4) {
                subject = 'Basic Assessment';
                icon = '📚';
                color = 'green-500';
            } else if (avgDifficulty > 0.7) {
                subject = 'Advanced Assessment';
                icon = '🎓';
                color = 'red-500';
            } else {
                subject = 'Standard Assessment';
                icon = '📊';
                color = 'blue-500';
            }
            
            const timeAgo = getTimeAgo(group[group.length - 1].timestamp);
            
            activities.push({
                id: `session_${group[group.length - 1].timestamp}`,
                subject,
                icon,
                color,
                timeAgo,
                accuracy,
                totalQuestions,
                correctAnswers,
                timestamp: group[group.length - 1].timestamp
            });
        });
        
        res.json({
            success: true,
            activities
        });
    } catch (error) {
        console.error('Recent activity error:', error);
        res.status(500).json({
            success: false,
            message: 'Failed to fetch recent activity'
        });
    }
});

// Helper function to calculate time ago
function getTimeAgo(timestamp) {
    const now = new Date();
    const time = new Date(timestamp);
    const diffInMinutes = Math.floor((now - time) / (1000 * 60));
    
    if (diffInMinutes < 1) return 'Just now';
    if (diffInMinutes < 60) return `${diffInMinutes} minutes ago`;
    
    const diffInHours = Math.floor(diffInMinutes / 60);
    if (diffInHours < 24) return `${diffInHours} hour${diffInHours > 1 ? 's' : ''} ago`;
    
    const diffInDays = Math.floor(diffInHours / 24);
    if (diffInDays < 7) return `${diffInDays} day${diffInDays > 1 ? 's' : ''} ago`;
    
    return time.toLocaleDateString();
}

// Update assessment data (called after each question)
app.post('/api/assessment/update', verifyToken, async (req, res) => {
    try {
        const userId = req.user.userId;
        const { questionId, difficulty, correct, timeSpent } = req.body;
        
        console.log('🎯 Updating assessment data:', { userId, questionId, difficulty, correct });
        
        // Convert difficulty string to number
        let difficultyValue = 0;
        if (typeof difficulty === 'string') {
            const difficultyMap = {
                'Very easy': 0.2,
                'Easy': 0.4,
                'Moderate': 0.6,
                'Difficult': 0.8,
                'Very difficult': 1.0
            };
            difficultyValue = difficultyMap[difficulty] || 0.5;
        } else {
            difficultyValue = parseFloat(difficulty) || 0.5;
        }
        
        console.log('🔄 Converted difficulty:', difficulty, '→', difficultyValue);
        
        let session = await Session.findOne({ userId });
        
        if (!session) {
            session = new Session({
                userId,
                ability: 0,
                questionsAnswered: 0,
                correctAnswers: 0,
                assessmentHistory: [],
                lastActivity: new Date()
            });
        }
        
        // Ensure ability is a valid number
        if (isNaN(session.ability)) {
            session.ability = 0;
        }
        
        // Update session data
        session.questionsAnswered += 1;
        if (correct) {
            session.correctAnswers += 1;
        }
        
        // Update ability using IRT-like calculation
        const expectedCorrect = 1 / (1 + Math.exp(-(session.ability - difficultyValue)));
        const abilityChange = correct ? 
            0.3 * (1 - expectedCorrect) : 
            -0.3 * expectedCorrect;
        
        session.ability += abilityChange;
        
        // Ensure ability remains a valid number
        if (isNaN(session.ability)) {
            session.ability = 0;
        }
        
        session.lastActivity = new Date();
        
        // Add to assessment history
        session.assessmentHistory.push({
            questionId,
            difficulty: difficultyValue, // Store as number
            correct,
            timestamp: new Date(),
            timeSpent: timeSpent || 0
        });
        
        await session.save();
        
        console.log('✅ Assessment data saved:', {
            ability: session.ability,
            totalQuestions: session.questionsAnswered,
            correctAnswers: session.correctAnswers
        });
        
        res.json({
            success: true,
            message: 'Assessment data updated',
            newAbility: Math.round(session.ability * 100) / 100,
            totalQuestions: session.questionsAnswered,
            accuracy: Math.round((session.correctAnswers / session.questionsAnswered) * 100)
        });
    } catch (error) {
        console.error('Assessment update error:', error);
        res.status(500).json({
            success: false,
            message: 'Failed to update assessment data'
        });
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, async () => {
    console.log(`🚀 Server running on port ${PORT}`);
    console.log(`🌐 Access the application at: http://localhost:${PORT}`);
    console.log('📧 Testing email configuration...');
    await testEmailConfiguration();
});