const jwt = require('jsonwebtoken');
require('dotenv').config();

// JWT Utility Functions
class JWTUtil {
    static generateToken(payload, expiresIn = '7d') {
        return jwt.sign(payload, process.env.JWT_SECRET, { expiresIn });
    }

    static verifyToken(token) {
        try {
            return jwt.verify(token, process.env.JWT_SECRET);
        } catch (error) {
            throw new Error('Invalid or expired token');
        }
    }

    static decodeToken(token) {
        return jwt.decode(token);
    }

    // Generate test tokens for development
    static generateTestTokens() {
        const testUser = {
            userId: '507f1f77bcf86cd799439011',
            email: 'test@example.com',
            firstName: 'Test',
            lastName: 'User'
        };

        return {
            shortToken: this.generateToken(testUser, '1h'),
            longToken: this.generateToken(testUser, '7d'),
            customToken: this.generateToken(testUser, '30d')
        };
    }
}

// Export for use in other files
module.exports = JWTUtil;

// If running directly, show some examples
if (require.main === module) {
    console.log('🔐 JWT Utility Examples\n');
    
    // Test payload
    const testPayload = {
        userId: '507f1f77bcf86cd799439011',
        email: 'test@adaptiq.com',
        firstName: 'John',
        lastName: 'Doe'
    };

    try {
        // Generate token
        const token = JWTUtil.generateToken(testPayload);
        console.log('Generated Token:');
        console.log(token);
        console.log('\nToken Length:', token.length, 'characters');

        // Verify token
        const verified = JWTUtil.verifyToken(token);
        console.log('\nVerified Payload:');
        console.log(verified);

        // Decode token (without verification)
        const decoded = JWTUtil.decodeToken(token);
        console.log('\nDecoded Token Header:');
        console.log(decoded);

        // Generate test tokens
        const testTokens = JWTUtil.generateTestTokens();
        console.log('\nTest Tokens Generated:');
        console.log('Short Token (1h):', testTokens.shortToken.substring(0, 50) + '...');
        console.log('Long Token (7d):', testTokens.longToken.substring(0, 50) + '...');
        console.log('Custom Token (30d):', testTokens.customToken.substring(0, 50) + '...');

    } catch (error) {
        console.error('❌ JWT Error:', error.message);
    }
}